"""
主入口：运行一次完整的"抓新闻 → 过滤分组 → AI 摘要 → 生成草稿 → 推送"流程。

用法：
    python src/main.py                       # 跑当天
    python src/main.py --date 2025-11-01     # 历史日期回测
    DRY_RUN=true python src/main.py          # 只生成不推送
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def setup_logger():
    """配置日志输出到终端 + 文件"""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    logger.add(
        ROOT / "logs" / "main.log",
        rotation="10 MB",
        retention="30 days",
        level=log_level,
        encoding="utf-8",
    )


def parse_args():
    parser = argparse.ArgumentParser(description="每日投资简报生成器")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="指定运行日期（YYYY-MM-DD），默认今天",
    )
    return parser.parse_args()


def main():
    setup_logger()
    args = parse_args()

    run_date = (
        datetime.strptime(args.date, "%Y-%m-%d").date()
        if args.date
        else datetime.now().date()
    )
    logger.info(f"========== 开始运行 {run_date} ==========")

    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logger.warning("DRY_RUN 模式：不会推送到微信")

    # ───── 步骤 1：采集新闻 ─────
    logger.info("[1/5] 采集新闻 ...")
    from src.collectors import news_cls, market_data

    raw_news = []
    try:
        raw_news += news_cls.fetch(window_hours=18)
    except Exception as e:
        logger.error(f"财联社采集失败：{e}")

    try:
        wind_snapshot = market_data.fetch_daily_snapshot(run_date)
    except Exception as e:
        logger.error(f"行情数据采集失败：{e}")
        wind_snapshot = None

    if not raw_news:
        logger.warning("未采集到任何新闻，退出")
        return

    # ───── 步骤 2：过滤 + 去重 + 板块分组 ─────
    logger.info("[2/5] 过滤分组 ...")
    from src.processors.filter import filter_and_group, load_sectors_config

    sectors_config = load_sectors_config()
    grouped = filter_and_group(raw_news, sectors_config)

    total_grouped = sum(len(v) for v in grouped.values())
    if total_grouped == 0:
        logger.warning("过滤后没有匹配任何板块的新闻，退出")
        return

    # ───── 步骤 3：调 DeepSeek 做摘要 + 点评 ─────
    logger.info("[3/5] AI 摘要 ...")
    from src.processors.summarizer import summarize_daily

    try:
        summary = summarize_daily(
            grouped,
            wind_snapshot=wind_snapshot,
            framework_path=str(ROOT / "prompts" / "framework.md"),
        )
    except Exception as e:
        logger.error(f"LLM 摘要生成失败：{e}")
        return

    # ───── 步骤 4：生成小红书格式草稿 ─────
    logger.info("[4/5] 生成草稿 ...")
    from src.processors.formatter import to_xiaohongshu_draft

    draft = to_xiaohongshu_draft(
        summary,
        wind_snapshot=wind_snapshot,
        run_date=run_date,
    )

    # ───── 步骤 5：推送到 Server 酱 ─────
    logger.info("[5/5] 推送 ...")
    if not dry_run:
        from src.publishers.serverchan import push

        try:
            push(
                title=f"📊 今日投资简报草稿 - {run_date}",
                content=draft.body_markdown,
            )
        except Exception as e:
            logger.error(f"推送失败：{e}")
    else:
        logger.info("DRY_RUN，跳过推送")

    logger.info(f"========== 完成 {run_date} ==========")
    logger.info(f"草稿路径：output/drafts/{run_date}/")


if __name__ == "__main__":
    main()
