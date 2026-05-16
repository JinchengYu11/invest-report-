"""
个股深度报告生成器。

支持 A 股（代码格式：688008.SH / 300750.SZ / 000001.SZ）。
流程：拉取行情 + 研报 + 财务 + 行情背景 → 组装提问 → 调 Dexter 合成报告。

用法：
    from src.qa.report import generate_report
    report = generate_report("688008.SH")
"""

import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import requests
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}


def _parse_code(stock_code: str) -> tuple[str, str]:
    """
    解析股票代码 → (新浪代码, 交易所前缀)。

    Examples:
        688008.SH → ("sh688008", "sh")
        300750.SZ → ("sz300750", "sz")
    """
    code = stock_code.strip().upper()
    if "." in code:
        parts = code.split(".")
        num, mkt = parts[0], parts[1].lower()
    else:
        # 六位数字 → 推测市场
        num = code
        if code.startswith(("688", "600", "601", "603", "605")):
            mkt = "sh"
        elif code.startswith(("000", "001", "002", "003", "300", "301")):
            mkt = "sz"
        else:
            mkt = "sz"
    return f"{mkt}{num}", mkt


def _fetch_stock_quote(stock_code: str) -> dict:
    """从新浪拉取个股实时行情"""
    sina_code, mkt = _parse_code(stock_code)
    url = f"http://hq.sinajs.cn/list={sina_code}"
    resp = requests.get(url, headers=SINA_HEADERS, timeout=10)
    resp.encoding = "gbk"

    raw = resp.text.split('"')[1]
    if not raw or raw.startswith("FAILED"):
        raise RuntimeError(f"未找到股票：{stock_code}")

    parts = raw.split(",")
    if len(parts) < 32:
        raise RuntimeError(f"行情数据不完整：{stock_code}")

    return {
        "name": parts[0],
        "open": float(parts[1]),
        "prev_close": float(parts[2]),
        "price": float(parts[3]),
        "high": float(parts[4]),
        "low": float(parts[5]),
        "volume": int(float(parts[8])),
        "amount": float(parts[9]),
        "date": parts[30],
        "time": parts[31] if len(parts) > 31 else "",
    }


def _fetch_reports(stock_code: str, limit: int = 8) -> list[dict]:
    """从东方财富拉取个股研报"""
    import akshare as ak

    code_num = stock_code.split(".")[0]
    try:
        df = ak.stock_research_report_em(symbol=code_num)
        if df is None or (hasattr(df, "empty") and df.empty):
            return []
        reports = []
        for _, row in df.head(limit).iterrows():
            reports.append({
                "title": str(row.get("报告名称", "")),
                "org": str(row.get("机构", "")),
                "date": str(row.get("日期", ""))[:10],
                "rating": str(row.get("东财评级", "")),
            })
        return reports
    except Exception as e:
        logger.warning(f"研报 API 失败（{stock_code}）：{e}")
        return []


def _fetch_market_context() -> str:
    """拉取大盘背景"""
    try:
        from src.collectors.market_data import fetch_daily_snapshot
        snap = fetch_daily_snapshot()
        if snap is None:
            return "（大盘数据不可用）"

        lines = ["【A 股大盘背景】"]
        for name, v in snap.index_changes.items():
            lines.append(f"  {name}：{v.get('pct', 'N/A')}%")
        if snap.cn10y:
            lines.append(f"  中国10Y国债：{snap.cn10y}%")
        if snap.us10y:
            lines.append(f"  美国10Y国债：{snap.us10y}%")

        extra = snap.extra
        if extra:
            top = extra.get("top_sectors", [])[:5]
            bot = extra.get("bottom_sectors", [])[:3]
            if top:
                top_str = "、".join(f"{s['name']}+{s['pct']}%" for s in top)
                lines.append(f"  领涨板块：{top_str}")
            if bot:
                bot_str = "、".join(f"{s['name']}{s['pct']}%" for s in bot)
                lines.append(f"  领跌板块：{bot_str}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"大盘数据拉取失败：{e}")
        return "（大盘数据不可用）"


def build_report_prompt(stock_code: str) -> str:
    """
    为给定股票组装一份深度分析的提问。

    Returns:
        组装好的提问文本，可直接喂给 Dexter
    """
    # 1) 行情
    try:
        quote = _fetch_stock_quote(stock_code)
    except Exception as e:
        raise RuntimeError(f"行情拉取失败：{e}")

    # 2) 研报
    reports = _fetch_reports(stock_code)

    # ── 组装提问 ──
    name = quote["name"]

    # 研报摘要
    report_lines = ""
    if reports:
        for r in reports[:4]:
            report_lines += f"  [{r['date']}] {r['org']} | {r['title']} | {r['rating']}\n"
    else:
        report_lines = "  （暂无）\n"

    # 大盘简况（只取科创50做参考）
    idx_hint = ""
    try:
        from src.collectors.market_data import fetch_daily_snapshot
        snap = fetch_daily_snapshot()
        if snap and snap.index_changes:
            sci50 = snap.index_changes.get("科创50", {})
            if sci50:
                idx_hint = f"科创50{sci50.get('pct',0):+.2f}%"
            if snap.cn10y:
                idx_hint += f"，CN10Y={snap.cn10y}%"
            if snap.us10y:
                idx_hint += f"，US10Y={snap.us10y}%"
    except Exception:
        pass

    prompt = (
        f"为{name}（{stock_code}）写个股深度分析。"
        f"最新价{quote['price']}元，昨收{quote['prev_close']}，"
        f"日涨跌{(quote['price']-quote['prev_close'])/quote['prev_close']*100:+.2f}%，"
        f"成交{quote['amount']/1e8:.1f}亿。"
        f"大盘：{idx_hint}。"
        f"研报：{report_lines}"
        f"请输出：1.估值与市场表现 2.产业链位置 3.近期催化剂与风险 "
        f"4.机构观点摘要 5.值得盯的指标（2-3个信号）。"
        f"冷静、不下买卖建议。用Markdown。"
    )
    return prompt


def generate_report(stock_code: str, timeout_seconds: int = 300) -> str:
    """
    生成个股深度报告。

    Args:
        stock_code: 股票代码，如 688008.SH
        timeout_seconds: Dexter 超时秒数

    Returns:
        报告全文（Markdown）
    """
    prompt = build_report_prompt(stock_code)
    logger.info(f"报告提问长度：{len(prompt)} 字符")

    from src.qa.bridge import ask_dexter
    return ask_dexter(
        prompt,
        enrich_with_market=False,  # 已在提问中自带大盘背景
        timeout_seconds=timeout_seconds,
    )


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    stock = sys.argv[1] if len(sys.argv) > 1 else "688008.SH"
    print(f"生成 {stock} 报告...\n")
    report = generate_report(stock, timeout_seconds=300)
    print(report)
