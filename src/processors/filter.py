"""
新闻过滤与板块分组。

处理流程：
  原始新闻 → 标题长度过滤 → 黑名单过滤 → 去重 → 板块关键词匹配 → 按板块分组 → 限额截断
"""

import difflib
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from loguru import logger

from src.utils.models import NewsItem


def load_sectors_config(config_path: Optional[str] = None) -> dict:
    """加载 sectors.yaml 配置文件"""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "sectors.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _match_keywords(text: str, keywords: List[str]) -> bool:
    """检查文本是否包含任意关键词（不区分大小写）"""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def filter_and_group(
    raw_news: List[NewsItem],
    sectors_config: Optional[dict] = None,
) -> Dict[str, List[NewsItem]]:
    """
    对原始新闻做过滤、去重、板块分组。

    Args:
        raw_news: 原始新闻列表
        sectors_config: sectors.yaml 内容，None 则自动加载

    Returns:
        {板块名: [NewsItem, ...], ...}，按 sectors.yaml 中定义的顺序
    """
    if sectors_config is None:
        sectors_config = load_sectors_config()

    sectors = sectors_config["sectors"]
    filters_cfg = sectors_config.get("filters", {})

    # ── 1. 标题长度过滤 ──
    min_len = filters_cfg.get("min_title_length", 10)
    news = [n for n in raw_news if len(n.title) >= min_len]
    logger.debug(f"标题长度过滤（≥{min_len}）：{len(raw_news)} → {len(news)}")

    # ── 2. 黑名单过滤 ──
    blacklist = filters_cfg.get("blacklist_keywords", [])
    if blacklist:
        before = len(news)
        news = [n for n in news if not _match_keywords(n.title, blacklist)]
        logger.debug(f"黑名单过滤：{before} → {len(news)}")

    # ── 3. 标题相似度去重 ──
    threshold = filters_cfg.get("dedup_similarity", 0.85)
    deduped: List[NewsItem] = []
    for n in news:
        is_dup = False
        for existing in deduped:
            ratio = difflib.SequenceMatcher(None, n.title, existing.title).ratio()
            if ratio >= threshold:
                is_dup = True
                break
        if not is_dup:
            deduped.append(n)
    logger.info(f"去重（相似度≥{threshold}）：{len(news)} → {len(deduped)}")
    news = deduped

    # ── 4. 板块关键词匹配 ──
    for item in news:
        search_text = f"{item.title} {item.content}"
        for sector in sectors:
            if _match_keywords(search_text, sector["keywords"]):
                item.sector = sector["name"]
                break

    # ── 5. 按板块分组 ──
    grouped: Dict[str, List[NewsItem]] = {}
    for sector in sectors:
        grouped[sector["name"]] = []

    for item in news:
        if item.sector:
            grouped[item.sector].append(item)

    # ── 6. 每个板块限额截断 ──
    max_per = filters_cfg.get("max_per_sector", 8)
    for sector_name, items in grouped.items():
        if len(items) > max_per:
            grouped[sector_name] = items[:max_per]

    # 日志
    total = 0
    for sector_name, items in grouped.items():
        logger.info(f"  [{sector_name}] {len(items)} 条")
        total += len(items)
    logger.info(f"过滤分组完成：{len(raw_news)} → {len(news)} → {total} 条（已分组）")

    return grouped
