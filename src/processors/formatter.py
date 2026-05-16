"""
小红书格式草稿生成器。

将 AI 摘要文本包装为 DraftPackage，保存到 output/drafts/日期/ 目录。
"""

import re
from datetime import date
from pathlib import Path
from typing import List, Optional

import yaml
from loguru import logger

from src.utils.models import DailySnapshot, DraftPackage


def _extract_hashtags(text: str, max_count: int = 8) -> List[str]:
    """从正文中提取 # 标签，去重保持顺序"""
    tags = re.findall(r"#[一-鿿\w]+", text)
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:max_count]


def _extract_title(text: str) -> str:
    """从正文提取标题：优先 ## 或 ** 开头的行，否则取首行"""
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("##") or line.startswith("**"):
            return line.lstrip("#").lstrip("*").strip()
    for line in text.split("\n"):
        if line.strip():
            return line.strip()[:50]
    return "今日投资简报"


def to_xiaohongshu_draft(
    summary_text: str,
    wind_snapshot: Optional[DailySnapshot] = None,
    run_date: Optional[date] = None,
    output_dir: Optional[str] = None,
) -> DraftPackage:
    """
    将 LLM 生成的简报文本打包为小红书草稿，保存到本地文件。

    Args:
        summary_text: LLM 返回的完整简报文本
        wind_snapshot: 市场数据快照（当前未使用，预留给图表生成）
        run_date: 运行日期，None 则今天
        output_dir: 输出目录，None 则自动生成 output/drafts/YYYY-MM-DD/

    Returns:
        DraftPackage 对象，含所有输出文件路径
    """
    if run_date is None:
        run_date = date.today()

    date_str = run_date.strftime("%Y-%m-%d")

    if output_dir is None:
        root = Path(__file__).resolve().parent.parent.parent
        output_dir = root / "output" / "drafts" / date_str
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    hashtags = _extract_hashtags(summary_text)
    title = _extract_title(summary_text)

    # 写正文 markdown
    body_path = output_dir / "body.md"
    with open(body_path, "w", encoding="utf-8") as f:
        f.write(summary_text)

    # 写元信息 yaml
    meta_path = output_dir / "meta.yaml"
    with open(meta_path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"date": date_str, "title": title, "hashtags": hashtags},
            f,
            allow_unicode=True,
            default_flow_style=False,
        )

    # ── 生成图表 ──
    cover_path = None
    chart_paths = []
    if wind_snapshot:
        try:
            from src.utils.chart import generate_cover, generate_market_overview
            cover_path = str(generate_cover(wind_snapshot, title, output_dir))
            overview_path = generate_market_overview(wind_snapshot, output_dir)
            if overview_path:
                chart_paths.append(str(overview_path))
        except Exception as e:
            logger.warning(f"图表生成失败：{e}")

    draft = DraftPackage(
        date=date_str,
        title=title,
        body_markdown=summary_text,
        hashtags=hashtags,
        cover_image_path=cover_path,
        chart_paths=chart_paths,
    )

    logger.info(f"草稿已保存 → {output_dir}")
    logger.info(f"  body.md  : {len(summary_text)} 字符")
    logger.info(f"  cover.png: {'✓' if cover_path else '✗'}, charts: {len(chart_paths)}")
    logger.info(f"  hashtags : {' '.join(hashtags) if hashtags else '(未提取到)'}")

    return draft
