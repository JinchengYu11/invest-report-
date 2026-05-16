"""
东方财富研报采集器。

源：https://data.eastmoney.com/report/
免费 JSONP 接口，无需登录。抓最近 2-3 天的券商研报。

用法：
    from src.collectors.news_report import fetch
    items = fetch(window_hours=48)
"""

import re
import time
import json
from datetime import datetime, timedelta
from typing import List

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.models import NewsItem

# 东方财富研报列表 JSONP API
REPORT_API = "https://reportapi.eastmoney.com/report/list"
REPORT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10))
def _fetch_reports_page(begin_date: str, end_date: str, page: int = 1) -> list[dict]:
    """
    调东方财富研报 JSONP 接口，返回一页数据。

    Args:
        begin_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        page: 页码

    Returns:
        研报字典列表
    """
    params = {
        "cb": "jQuery",
        "industryCode": "*",
        "pageSize": "30",
        "pageNo": str(page),
        "beginTime": begin_date,
        "endTime": end_date,
        "qType": "0",
        "sortTypes": "-1",
        "sortColumns": "publishDate",
        "source": "WEB",
        "client": "WEB",
    }
    resp = requests.get(REPORT_API, params=params, headers=REPORT_HEADERS, timeout=15)
    resp.raise_for_status()

    # JSONP → JSON
    m = re.search(r"jQuery\((.*)\)", resp.text, re.DOTALL)
    if not m:
        raise RuntimeError("JSONP 解析失败")
    data = json.loads(m.group(1))

    if not data or "data" not in data:
        raise RuntimeError(f"API 返回异常：无 data 字段")

    return data.get("data", [])


def fetch(window_hours: int = 48) -> List[NewsItem]:
    """
    采集最近 N 小时内的券商研报。

    抓最近 3 天数据，按板块关键词做初步匹配。

    Args:
        window_hours: 时间窗口

    Returns:
        NewsItem 列表（source = 券商简称，content = 摘要来自标题）
    """
    now = datetime.now()
    begin_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    end_date = now.strftime("%Y-%m-%d")
    cutoff = now - timedelta(hours=window_hours)

    all_items: List[NewsItem] = []
    seen_titles = set()

    for page in range(1, 4):  # 最多 3 页 = 90 条
        try:
            reports = _fetch_reports_page(begin_date, end_date, page)
        except Exception as e:
            logger.warning(f"研报第 {page} 页采集失败：{e}")
            continue

        if not reports:
            break

        for r in reports:
            title = r.get("title", "")
            if not title:
                continue

            # 基础去重
            title_key = re.sub(r"[^一-鿿a-zA-Z0-9]", "", title[:30])
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)

            # 解析时间
            pub_str = r.get("publishDate", "")
            try:
                pub_date = datetime.strptime(pub_str[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if pub_date < cutoff:
                continue

            org = r.get("orgSName", "券商")
            stock = r.get("stockName", "")
            rating = r.get("emRatingValue", "")
            industry = r.get("industryName", "")

            # 组装 content（研报无正文，用标题+机构+评级代替）
            parts = [f"【{org}】"]
            if stock:
                parts.append(f"覆盖标的：{stock}")
            if rating:
                rating_map = {"1": "买入", "2": "增持", "3": "中性", "4": "减持", "5": "卖出"}
                parts.append(f"评级：{rating_map.get(rating, rating)}")
            if industry:
                parts.append(f"行业：{industry}")

            all_items.append(NewsItem(
                title=title,
                content="；".join(parts[1:]) if len(parts) > 1 else "",
                url=r.get("encodeUrl", ""),
                source=f"📄 {org}",
                published_at=pub_date,
            ))

        if len(reports) < 30:
            break

        time.sleep(0.5)

    all_items.sort(key=lambda x: x.published_at or datetime.min, reverse=True)
    logger.info(f"研报采集完成：{len(all_items)} 篇（{window_hours}h 内）")
    return all_items


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    items = fetch(window_hours=72)
    for item in items[:12]:
        pub = item.published_at.strftime("%m-%d %H:%M") if item.published_at else "??"
        print(f"[{pub}] {item.source}: {item.title[:60]}")
