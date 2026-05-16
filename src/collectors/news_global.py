"""
Google News RSS 采集器。

聚合 Reuters / Bloomberg / CNBC 等全球一手财经新闻，
按投资板块关键词搜索，与财联社（A股快讯）互补。

来源：Google News RSS（免费，无需 API Key）
用法：
    from src.collectors.news_global import fetch
    news = fetch(window_hours=24)
"""

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.models import NewsItem

# ─── 搜索查询配置 ────────────────────────────────────────────────

# 每个板块对应一组 Google News 搜索词
# Google News 限制：单次查询最多约 100 条结果，返回最近 30 天内容
SECTOR_QUERIES = {
    "AI算力": [
        '(Nvidia OR NVIDIA OR "AI chip" OR H200 OR B200 OR HBM) '
        'OR (Anthropic OR OpenAI OR "large language model" OR LLM) '
        'OR ("optical module" OR "data center" OR "AI server")',
    ],
    "人形机器人": [
        '("humanoid robot" OR "Figure AI" OR "Tesla Optimus" OR robotics) '
        'OR ("harmonic drive" OR "ball screw" OR "robot actuator")',
    ],
    "半导体": [
        '(semiconductor OR TSMC OR ASML OR "chip export" OR "entity list") '
        'OR ("advanced packaging" OR CoWoS OR chiplet OR lithography) '
        'OR (SMIC OR Huawei OR "chip ban" OR "export control")',
    ],
    "智能驾驶": [
        '("autonomous driving" OR "FSD" OR "Robotaxi" OR "smart driving") '
        'OR (BYD OR "Xpeng" OR "NIO" OR "Li Auto" OR "Tesla China") '
        'OR ("lidar" OR "Horizon Robotics" OR "city NOA")',
    ],
    "海外宏观": [
        '("Federal Reserve" OR FOMC OR "Fed rate" OR "US Treasury yield") '
        'OR ("China 10Y" OR PBOC OR "China economy" OR "China stimulus") '
        'OR ("US CPI" OR "nonfarm payroll" OR "global market")',
    ],
}

# Google News RSS endpoint
RSS_BASE = "https://news.google.com/rss/search"
RSS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


def _strip_html(text: str) -> str:
    """去除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", text)


def _parse_google_news_date(pub_date_str: str) -> datetime:
    """
    解析 Google News RSS 的 pubDate，返回原生 datetime（去时区）。
    格式：Thu, 14 May 2026 12:08:50 GMT
    """
    from email.utils import parsedate_to_datetime
    dt = parsedate_to_datetime(pub_date_str)
    return dt.replace(tzinfo=None)  # 去掉 tz 信息，与 cutoff 对齐


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def _fetch_rss(query: str, lang: str = "en", limit: int = 20) -> List[NewsItem]:
    """
    调 Google News RSS 搜索，返回 NewsItem 列表。

    Args:
        query: 搜索词
        lang: 语言 en / zh
        limit: 最多返回条数
    """
    hl = "en-US" if lang == "en" else "zh-CN"
    gl = "US" if lang == "en" else "CN"
    ceid = f"{gl}:{lang}"

    params = {
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    }
    resp = requests.get(RSS_BASE, params=params, headers=RSS_HEADERS, timeout=15)
    resp.raise_for_status()

    # Google News RSS 内容在 resp.text 中，命名空间需要处理
    root = ET.fromstring(resp.text)
    ns = {"media": "http://search.yahoo.com/mrss/"}

    items = []
    for el in root.iter("item"):
        title_el = el.find("title")
        link_el = el.find("link")
        desc_el = el.find("description")
        pubdate_el = el.find("pubDate")
        source_el = el.find("source")

        if title_el is None:
            continue

        title = _strip_html(title_el.text or "")
        link = link_el.text if link_el is not None else ""

        # 描述中提取纯文本（去除 HTML）
        desc_raw = desc_el.text if desc_el is not None else ""
        content_text = _strip_html(desc_raw).strip()

        # 来源从 link 中提取域名
        source = "Global"
        if link:
            m = re.search(r"https?://(?:www\.)?([^/]+)", link)
            if m:
                source = m.group(1)

        # 子来源（source 标签）
        if source_el is not None and source_el.text:
            source = source_el.text

        pub_date = datetime.now()
        if pubdate_el is not None and pubdate_el.text:
            try:
                pub_date = _parse_google_news_date(pubdate_el.text)
            except Exception:
                pass

        items.append(NewsItem(
            title=title,
            content=content_text[:500] if content_text else "",
            url=link,
            source=source,
            published_at=pub_date,
        ))

        if len(items) >= limit:
            break

    return items


def fetch(window_hours: int = 24) -> List[NewsItem]:
    """
    采集 Google News 全球财经新闻。

    按板块逐组查询，自动去重（按 title 相似度）。
    每个板块搜索英文 + 中文两组词。

    Args:
        window_hours: 只保留最近 N 小时内的新闻

    Returns:
        NewsItem 列表，已去重
    """
    cutoff = datetime.now() - timedelta(hours=window_hours)
    all_items: List[NewsItem] = []
    seen_titles = set()

    for sector_name, queries in SECTOR_QUERIES.items():
        for query in queries:
            try:
                items = _fetch_rss(query, lang="en", limit=15)
                logger.info(f"Google News [{sector_name}] 英文：{len(items)} 条 → query: {query[:60]}...")

                # 也搜中文
                items_cn = _fetch_rss(query, lang="zh", limit=10)
                items += items_cn
                logger.info(f"Google News [{sector_name}] 中文：+{len(items_cn)} 条")

                for item in items:
                    # 去重（简单 title 去重，忽略大小写和标点）
                    title_key = re.sub(r"[^a-zA-Z0-9一-鿿]", "", item.title.lower())
                    if title_key in seen_titles:
                        continue
                    seen_titles.add(title_key)

                    if item.published_at and item.published_at < cutoff:
                        continue

                    item.sector = sector_name
                    all_items.append(item)

                time.sleep(1)  # 避免太快被 Google 限流
            except Exception as e:
                logger.warning(f"Google News [{sector_name}] 采集失败：{e}")

    # 按时间倒序
    all_items.sort(key=lambda x: x.published_at or datetime.min, reverse=True)

    logger.info(f"Google News 采集完成：{len(all_items)} 条（去重后，{window_hours}h 内）")
    return all_items


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    items = fetch(window_hours=48)
    for item in items[:15]:
        print(f"[{item.sector}] {item.source}: {item.title[:70]}")
