"""
A 股行情数据工具 — 为 Dexter 提供 A 股市场上下文。

在调用 Dexter 之前，拉取当日行情数据，格式化为纯文本上下文，
拼入用户问题中，让 Dexter 回答时能看到 A 股实时数据。

用法：
    from src.qa.wind_tools import enrich_question
    enriched = enrich_question("今天科技板块怎么看？")
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# 确保项目根在 sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def _format_snapshot(snapshot) -> str:
    """将 DailySnapshot 格式化为自然语言上下文"""
    lines = ["【A 股今日行情数据】"]

    # 指数
    indices = snapshot.index_changes
    if indices:
        idx_strs = []
        for name, v in indices.items():
            close = v.get("close", "N/A")
            pct = v.get("pct", "N/A")
            sign = "+" if (pct if isinstance(pct, (int, float)) else 0) >= 0 else ""
            idx_strs.append(f"{name} {close}（{sign}{pct}%）")
        lines.append("主要指数：" + "，".join(idx_strs))
    else:
        lines.append("主要指数：暂无数据")

    # 国债
    yields_parts = []
    if snapshot.cn10y:
        yields_parts.append(f"中国10Y国债 {snapshot.cn10y}%")
    if snapshot.us10y:
        yields_parts.append(f"美国10Y国债 {snapshot.us10y}%")
    if yields_parts:
        lines.append("国债收益率：" + "，".join(yields_parts))

    # 北向
    if snapshot.north_flow:
        lines.append(f"北向资金净买额：{snapshot.north_flow} 亿元")

    # 行业板块
    extra = snapshot.extra
    if extra:
        top = extra.get("top_sectors", [])[:5]
        bot = extra.get("bottom_sectors", [])[:3]
        if top:
            top_str = "、".join(f"{s['name']}+{s['pct']}%" for s in top)
            lines.append(f"领涨板块：{top_str}")
        if bot:
            bot_str = "、".join(f"{s['name']}{s['pct']}%" for s in bot)
            lines.append(f"领跌板块：{bot_str}")

    return "\n".join(lines)


def enrich_question(question: str) -> str:
    """
    给用户问题附加上当日 A 股行情数据上下文。

    Args:
        question: 用户原始问题

    Returns:
        带有行情上下文的问题文本
    """
    try:
        from src.collectors.market_data import fetch_daily_snapshot
        snap = fetch_daily_snapshot()
        if snap is None:
            logger.warning("行情数据不可用，使用原始问题")
            return question
        context = _format_snapshot(snap)
        return f"{context}\n\n---\n用户问题：{question}"
    except Exception as e:
        logger.warning(f"行情数据增强失败：{e}")
        return question


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    q = enrich_question("今天A股科技板块怎么样？")
    print(q)
