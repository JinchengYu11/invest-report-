"""
财联社电报采集器。

来源：https://www.cls.cn/telegraph
财联社电报有公开的 JSON 接口，无需登录。

返回：List[NewsItem]
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.models import NewsItem


CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "news_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://www.cls.cn/nodeapi/updateTelegraphList"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.cls.cn/telegraph",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _fetch_page(last_time: int = 0) -> List[dict]:
    """
    抓取一页电报。

    Args:
        last_time: Unix 时间戳，0 表示最新。用于翻页（向前翻）。

    Returns:
        电报原始 dict 列表
    """
    params = {
        "app": "CailianpressWeb",
        "category": "",
        "lastTime": last_time,
        "last_time": last_time,
        "os": "web",
        "refresh_type": 1,
        "rn": 50,
        "sv": "7.7.5",
    }
    resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errno", 0) != 0:
        logger.warning(f"财联社接口返回错误：{data.get('errmsg')}")
        return []
    return data.get("data", {}).get("roll_data", [])


def fetch(window_hours: int = 18, use_cache: bool = True) -> List[NewsItem]:
    """
    抓取过去 window_hours 小时内的财联社电报。

    Args:
        window_hours: 时间窗口（小时）
        use_cache: 当日是否复用缓存（调试时打开）

    Returns:
        NewsItem 列表
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"cls_{today_str}.json"

    if use_cache and cache_file.exists():
        logger.info(f"使用缓存：{cache_file.name}")
        with open(cache_file, "r", encoding="utf-8") as f:
            raw_items = json.load(f)
    else:
        cutoff = datetime.now() - timedelta(hours=window_hours)
        cutoff_ts = int(cutoff.timestamp())

        raw_items: List[dict] = []
        last_time = 0
        page = 0
        max_pages = 20   # 防止无限翻页

        while page < max_pages:
            page += 1
            try:
                batch = _fetch_page(last_time)
            except Exception as e:
                logger.error(f"财联社抓取第 {page} 页失败：{e}")
                break

            if not batch:
                break

            raw_items.extend(batch)
            oldest_ts = min(it.get("ctime", 0) for it in batch)
            if oldest_ts <= cutoff_ts:
                break
            last_time = oldest_ts
            time.sleep(0.5)   # 礼貌停顿

        # 写缓存
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(raw_items, f, ensure_ascii=False)

    # 转 NewsItem
    items: List[NewsItem] = []
    cutoff = datetime.now() - timedelta(hours=window_hours)

    for it in raw_items:
        ctime = it.get("ctime")
        if not ctime:
            continue
        pub_at = datetime.fromtimestamp(ctime)
        if pub_at < cutoff:
            continue

        title = it.get("title") or it.get("brief") or ""
        content = it.get("content") or ""
        # 财联社电报有时 title 空，brief 是正文摘要
        if not title and content:
            title = content[:50]

        if not title.strip():
            continue

        items.append(
            NewsItem(
                title=title.strip(),
                content=content.strip(),
                url=it.get("shareurl", ""),
                source="财联社",
                published_at=pub_at,
            )
        )

    logger.info(f"财联社抓取完成：{len(items)} 条")
    return items


# ───── 单独跑测试 ─────
if __name__ == "__main__":
    import sys
    logger.remove()
    logger.add(sys.stderr, level="DEBUG")

    news = fetch(window_hours=12, use_cache=False)
    print(f"\n共 {len(news)} 条\n")
    for n in news[:10]:
        print(n.short_repr())
