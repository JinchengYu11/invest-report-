"""
AI 摘要与点评模块。

加载投资框架 + prompt 模板，填入市场数据和分组新闻，调用 DeepSeek 生成简报。
"""

from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from src.utils.llm import LLMClient
from src.utils.models import DailySnapshot, NewsItem


def _load_text(filepath: str) -> str:
    """读取文本文件"""
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def _format_sectorized_news(grouped_news: Dict[str, List[NewsItem]]) -> str:
    """将分组新闻格式化为 LLM 可读的 Markdown 文本"""
    lines = []
    for sector_name, items in grouped_news.items():
        if not items:
            lines.append(f"### {sector_name}\n（今日无相关新闻）\n")
            continue
        lines.append(f"### {sector_name}")
        for i, item in enumerate(items, 1):
            pub_time = item.published_at.strftime("%H:%M") if item.published_at else "未知"
            lines.append(f"{i}. **{item.title}**")
            if item.content:
                lines.append(f"   > {item.content[:200]}")
            lines.append(f"   来源：{item.source} · {pub_time}")
            lines.append("")
    return "\n".join(lines)


def summarize_daily(
    grouped_news: Dict[str, List[NewsItem]],
    wind_snapshot: Optional[DailySnapshot] = None,
    framework_path: Optional[str] = None,
    template_path: Optional[str] = None,
) -> str:
    """
    调用 LLM 生成每日投资简报。

    Args:
        grouped_news: 按板块分组的新闻，{板块名: [NewsItem, ...]}
        wind_snapshot: Wind 市场数据快照，None 时使用占位文本
        framework_path: 投资框架文件路径
        template_path: prompt 模板路径

    Returns:
        LLM 生成的完整简报文本
    """
    root = Path(__file__).resolve().parent.parent.parent

    if framework_path is None:
        framework_path = str(root / "prompts" / "framework.md")
    if template_path is None:
        template_path = str(root / "prompts" / "daily_brief.txt")

    framework = _load_text(framework_path)
    template = _load_text(template_path)

    # ── 格式化市场数据 ──
    if wind_snapshot:
        date_str = wind_snapshot.date
        if wind_snapshot.index_changes:
            index_lines = []
            for k, v in wind_snapshot.index_changes.items():
                close = v.get("close", "N/A")
                pct = v.get("pct", "N/A")
                index_lines.append(f"  {k}：收盘 {close}，涨跌 {pct}%")
            index_str = "\n".join(index_lines)
        else:
            index_str = "（暂无指数数据）"
        north_flow = f"{wind_snapshot.north_flow} 亿元" if wind_snapshot.north_flow else "暂无"
        cn10y = f"{wind_snapshot.cn10y}%" if wind_snapshot.cn10y else "暂无"
        cn10y_change = str(wind_snapshot.cn10y_change_bp) if wind_snapshot.cn10y_change_bp else "暂无"
        us10y = f"{wind_snapshot.us10y}%" if wind_snapshot.us10y else "暂无"
        us10y_change = str(wind_snapshot.us10y_change_bp) if wind_snapshot.us10y_change_bp else "暂无"
    else:
        date_str = "（Wind 不可用）"
        index_str = "（Wind 数据暂不可用，请手动查看）"
        north_flow = "暂无"
        cn10y = "暂无"
        cn10y_change = "暂无"
        us10y = "暂无"
        us10y_change = "暂无"

    # ── 填模板 ──
    prompt = template.format(
        framework=framework,
        date=date_str,
        index_changes=index_str,
        north_flow=north_flow,
        cn10y=cn10y,
        cn10y_change=cn10y_change,
        us10y=us10y,
        us10y_change=us10y_change,
        sectorized_news=_format_sectorized_news(grouped_news),
    )

    logger.info("调用 LLM 生成每日简报...")
    client = LLMClient()
    messages = [{"role": "user", "content": prompt}]
    result = client.chat(messages)
    logger.info(f"LLM 返回 {len(result)} 字符")
    return result
