"""
免费行情数据采集器。

替代 Wind，使用公开 API 获取每日行情快照：

数据源：
  - A 股指数 → 新浪财经（稳定，无需 API Key）
  - 行业板块涨跌榜 → 东方财富
  - 中国 10Y 国债收益率 → akshare（英为财情源）
  - 美国 10Y 国债收益率 → akshare（英为财情源）
  - 北向资金净买额 → 东方财富（收盘后有延迟）

用法：
    from src.collectors.market_data import fetch_daily_snapshot
    snap = fetch_daily_snapshot(run_date)
"""

from datetime import date, datetime
from typing import Optional

import requests
from loguru import logger

from src.utils.models import DailySnapshot


# ─── 新浪财经指数 API ──────────────────────────────────────────────

# 新浪接口的股票代码对照
SINA_INDEX_CODES = {
    "上证指数": "s_sh000001",
    "深证成指": "s_sz399001",
    "创业板指": "s_sz399006",
    "科创50":   "s_sh000688",
    "沪深300":  "s_sh000300",
}

SINA_API = "http://hq.sinajs.cn/list="
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

# 东方财富 headers（User-Agent 必填，否则 502）
EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}

# 跳过系统代理，直连
NO_PROXY = {"http": None, "https": None}


def _fetch_index_prices() -> dict:
    """
    从新浪财经拉取主要A股指数的最新价和涨跌幅。

    新浪返回格式（逗号分隔）：
        名称, 最新价, 涨跌额, 涨跌幅%, 成交量, 成交额

    Returns:
        {"上证指数": {"close": 3200.5, "pct": 0.5}, ...}
    """
    codes = ",".join(SINA_INDEX_CODES.values())
    url = SINA_API + codes

    resp = requests.get(url, headers=SINA_HEADERS, timeout=10)
    resp.raise_for_status()
    resp.encoding = "gbk"

    result = {}
    code_to_name = {v: k for k, v in SINA_INDEX_CODES.items()}

    for line in resp.text.strip().split("\n"):
        if not line.strip():
            continue
        # var hq_str_s_sh000001="上证指数,4135.39,-42.53,-1.02,7331623,151924003";
        parts = line.split('="')
        if len(parts) != 2:
            continue
        code_key = parts[0].replace("var hq_str_", "")
        values = parts[1].rstrip('";').split(",")
        if len(values) < 4:
            continue

        name = code_to_name.get(code_key, values[0])
        result[name] = {
            "close": float(values[1]),
            "pct": float(values[3]),
        }

    if not result:
        raise RuntimeError(f"新浪指数API返回为空")
    return result


# ─── 行业板块 → 东方财富 ─────────────────────────────────────────

SECTOR_API = "https://push2.eastmoney.com/api/qt/clist/get"


def _fetch_top_sectors(top_n: int = 10) -> list[dict]:
    """
    拉取当日涨幅最大的行业板块。

    Returns:
        [{"name": "机器人", "pct": 5.89}, ...]
    """
    params = {
        "pn": "1",
        "pz": str(top_n),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90+t:2",
        "fields": "f3,f14",      # f3=涨跌幅, f14=板块名
    }
    resp = requests.get(
        SECTOR_API, params=params, headers=EM_HEADERS,
        timeout=10, proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("rc") != 0 or not data.get("data"):
        raise RuntimeError(f"板块API返回异常：{data}")

    sectors = []
    for item in data["data"].get("diff", []):
        sectors.append({
            "name": item.get("f14", ""),
            "pct": item.get("f3"),
        })
    return sectors


def _fetch_top_sectors_declining(top_n: int = 5) -> list[dict]:
    """拉取跌幅最大的行业板块"""
    params = {
        "pn": "1",
        "pz": str(top_n),
        "po": "0",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": "m:90+t:2",
        "fields": "f3,f14",
    }
    resp = requests.get(
        SECTOR_API, params=params, headers=EM_HEADERS,
        timeout=10, proxies={"http": None, "https": None},
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("rc") != 0 or not data.get("data"):
        raise RuntimeError(f"板块API返回异常：{data}")

    sectors = []
    for item in data["data"].get("diff", []):
        sectors.append({
            "name": item.get("f14", ""),
            "pct": item.get("f3"),
        })
    return sectors


# ─── 中美 10Y 国债 → akshare（英为财情源）────────────────────────


def _fetch_bond_yields(run_date: date) -> dict:
    """
    获取中国和美国 10 年期国债收益率。

    使用 akshare 的 bond_zh_us_rate，数据源自英为财情 (Investing.com)。
    历史回测友好——可查询任意交易日（start_date 往回查）。

    Returns:
        {"cn10y": 1.7658, "us10y": 4.59}
    """
    import akshare as ak

    from datetime import timedelta

    # start_date 往前推 5 天，因为当天数据收盘后才出库
    start = (run_date - timedelta(days=5)).strftime("%Y-%m-%d")

    df = ak.bond_zh_us_rate(start_date=start)
    if df.empty:
        raise RuntimeError("未拉取到国债收益率数据")

    # 取最新一行（最近交易日）
    latest = df.iloc[-1]
    return {
        "cn10y": float(latest["中国国债收益率10年"]),
        "us10y": float(latest["美国国债收益率10年"]),
    }


# ─── 北向资金 → 东方财富 ─────────────────────────────────────────

HSGT_API = "https://push2.eastmoney.com/api/qt/kamt.kline/get"


def _fetch_north_flow(run_date: date) -> Optional[float]:
    """
    拉取当日北向资金净买额（亿元）。

    北向 = 沪股通北向 + 深股通北向。
    数据非实时，通常 T 日收盘后更新。当日数据尚未出库时返回 None。

    Returns:
        净买额（亿元），或 None
    """
    target_date = run_date.strftime("%Y-%m-%d")

    # klt=101 日线，获取最近 5 条
    params = {
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "klt": "101",
        "lmt": "5",
    }
    resp = requests.get(
        HSGT_API, params=params, headers=EM_HEADERS,
        timeout=10, proxies=NO_PROXY,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("rc") != 0 or not data.get("data"):
        logger.warning(f"北向资金API返回异常：{data}")
        return None

    north_total = None
    for direction_key in ["hk2sh", "hk2sz"]:
        klines = data["data"].get(direction_key, [])
        for kline in klines:
            parts = kline.split(",")
            if parts[0] == target_date:
                # f54=当日净买额(万元)
                net = float(parts[3]) if len(parts) > 3 else 0
                if north_total is None:
                    north_total = 0.0
                north_total += net / 10000    # 万元 → 亿元

    return north_total


# ─── 主入口 ───────────────────────────────────────────────────────


def fetch_daily_snapshot(run_date: Optional[date] = None) -> Optional[DailySnapshot]:
    """
    从免费公开 API 获取每日市场数据快照。

    每个数据源独立 try/except，单个失败不影响整体。
    所有数据源均失败时返回 None。

    Args:
        run_date: 查询日期，None 则今天

    Returns:
        DailySnapshot
    """
    if run_date is None:
        run_date = date.today()
    date_str = run_date.strftime("%Y-%m-%d")

    snapshot = DailySnapshot(date=date_str)
    had_any_success = False

    # 1) A 股指数
    try:
        snapshot.index_changes = _fetch_index_prices()
        logger.info(f"指数行情：{len(snapshot.index_changes)} 个指数")
        had_any_success = True
    except Exception as e:
        logger.warning(f"指数行情拉取失败：{e}")

    # 2) 国债收益率
    try:
        yields = _fetch_bond_yields(run_date)
        snapshot.cn10y = yields["cn10y"]
        snapshot.us10y = yields["us10y"]
        logger.info(f"国债收益率：CN10Y={snapshot.cn10y}%, US10Y={snapshot.us10y}%")
        had_any_success = True
    except Exception as e:
        logger.warning(f"国债收益率拉取失败：{e}")

    # 3) 北向资金
    try:
        north = _fetch_north_flow(run_date)
        if north is not None:
            snapshot.north_flow = round(north, 2)
            logger.info(f"北向资金：{snapshot.north_flow} 亿元")
        else:
            logger.info(f"北向资金：{date_str} 数据尚未出库")
        had_any_success = True
    except Exception as e:
        logger.warning(f"北向资金拉取失败：{e}")

    # 4) 行业板块涨跌榜
    try:
        top_up = _fetch_top_sectors(10)
        top_down = _fetch_top_sectors_declining(5)
        snapshot.extra = {
            "top_sectors": top_up,
            "bottom_sectors": top_down,
        }
        logger.info(f"行业板块：领涨 {len(top_up)} 个，领跌 {len(top_down)} 个")
        had_any_success = True
    except Exception as e:
        logger.warning(f"行业板块拉取失败：{e}")

    if not had_any_success:
        logger.error("所有数据源拉取失败，返回 None")
        return None

    return snapshot


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    snap = fetch_daily_snapshot()
    if snap:
        print(f"\n===== {snap.date} 市场快照 =====")
        print(f"指数：{snap.index_changes}")
        print(f"CN10Y: {snap.cn10y}%")
        print(f"US10Y: {snap.us10y}%")
        print(f"北向净买额: {snap.north_flow} 亿元")
        extra = snap.extra
        if extra:
            top = extra.get("top_sectors", [])
            bot = extra.get("bottom_sectors", [])
            print(f"领涨板块：{[s['name'] + ' +' + str(s['pct']) + '%' for s in top[:5]]}")
            print(f"领跌板块：{[s['name'] + ' ' + str(s['pct']) + '%' for s in bot[:3]]}")
