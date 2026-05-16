"""
封面图 + 图表生成。

为每日投资备忘录生成小红书封面图（900×1200）。
包含：日期 / 标题 / 指数行情 / 板块涨跌 / 国债收益率。

用法：
    from src.utils.chart import generate_cover
    path = generate_cover(snapshot, "今日AI回调加剧...", output_dir)
"""

from datetime import date
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # 无 GUI 后端
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import yaml
from loguru import logger


# ─── 字体设置 ──────────────────────────────────────────────────────

def _setup_font():
    """设置中文字体，优先 PingFang SC（macOS 自带）"""
    for fname in ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS", "sans-serif"]:
        try:
            fm.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [fname]
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue
    logger.warning("未找到中文字体，图表中文可能显示为方框")


_setup_font()


# ─── 色彩主题 ──────────────────────────────────────────────────────

BG_DARK = "#1a1a2e"
BG_CARD = "#16213e"
ACCENT_RED = "#e94560"
ACCENT_GREEN = "#0f9b58"
TEXT_WHITE = "#f0f0f0"
TEXT_GREY = "#a0a0b0"


def _load_cover_config():
    """从 settings.yaml 读取封面图配置"""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        settings = yaml.safe_load(f)
    cover = settings["output"]["cover_image"]
    return cover.get("width", 900), cover.get("height", 1200)


# ─── 封面图 ────────────────────────────────────────────────────────


def generate_cover(
    snapshot,          # DailySnapshot
    title: str,
    output_dir: Path,
) -> Path:
    """
    生成小红书风格封面图（900×1200）。

    Args:
        snapshot: 市场数据快照
        title: 简报标题（20-35 字）
        output_dir: 输出目录

    Returns:
        封面图文件路径
    """
    width, height = _load_cover_config()
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG_DARK)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.axis("off")

    # 背景
    ax.fill([0, width, width, 0], [0, 0, height, height], color=BG_DARK)

    # ── 顶栏 ──
    ax.fill([0, width, width, 0], [height - 80, height - 80, height, height],
            color=BG_CARD, alpha=0.5)

    # 日期
    date_str = snapshot.date
    ax.text(40, height - 30, date_str, fontsize=16, color=TEXT_GREY,
            va="center", fontweight="light")

    # 右上角标签
    ax.text(width - 40, height - 30, "投资备忘录", fontsize=14, color=TEXT_GREY,
            va="center", ha="right", fontweight="light")

    # ── 标题 ──
    title_lines = _wrap_text(title, max_chars=18, max_lines=3)
    y_title = height - 150
    for i, line in enumerate(title_lines):
        ax.text(40, y_title - i * 48, line, fontsize=28, color=TEXT_WHITE,
                va="top", fontweight="bold")

    # ── 分隔线 ──
    y_sep = y_title - len(title_lines) * 48 - 40
    ax.plot([40, width - 40], [y_sep, y_sep], color=ACCENT_RED, linewidth=2, alpha=0.6)

    # ── 指数行情 ──
    y_idx = y_sep - 50
    ax.text(40, y_idx, "A 股指数", fontsize=14, color=TEXT_GREY, va="top")

    indices = snapshot.index_changes
    if indices:
        idx_items = list(indices.items())
        cols = 3
        col_w = (width - 80) / cols
        for i, (name, val) in enumerate(idx_items[:6]):
            col = i % cols
            row = i // cols
            x_pos = 40 + col * col_w
            y_pos = y_idx - 50 - row * 70

            pct = val.get("pct", 0)
            close_val = val.get("close", 0)
            color = ACCENT_RED if pct >= 0 else ACCENT_GREEN

            ax.text(x_pos, y_pos, name, fontsize=12, color=TEXT_GREY, va="bottom")
            ax.text(x_pos, y_pos - 22, f"{close_val:.0f}", fontsize=18, color=TEXT_WHITE, va="bottom")
            ax.text(x_pos, y_pos - 46, f"{pct:+.2f}%", fontsize=14, color=color, va="bottom",
                    fontweight="bold")

    # ── 板块涨跌 ──
    y_sector_base = y_idx - 50 - ((len(idx_items) - 1) // 3 + 1) * 70 - 50
    extra = snapshot.extra
    if extra:
        top_sectors = extra.get("top_sectors", [])[:5]
        if top_sectors:
            ax.text(40, y_sector_base, "今日领涨板块", fontsize=14, color=TEXT_GREY, va="top")
            y_s = y_sector_base - 35
            for s in top_sectors[:5]:
                tag = f"  {s['name']}  +{s['pct']}%"
                ax.text(40, y_s, tag, fontsize=12, color=ACCENT_RED, va="top")
                y_s -= 26

    # ── 国债收益率 ──
    y_bond = y_sector_base - 180
    ax.text(40, y_bond, "国债收益率", fontsize=14, color=TEXT_GREY, va="top")
    cn_str = f"CN 中国10Y  {snapshot.cn10y}%" if snapshot.cn10y else "CN 中国10Y  --"
    us_str = f"US 美国10Y  {snapshot.us10y}%" if snapshot.us10y else "US 美国10Y  --"
    ax.text(40, y_bond - 35, cn_str, fontsize=14, color=TEXT_WHITE, va="top")
    ax.text(40, y_bond - 60, us_str, fontsize=14, color=TEXT_WHITE, va="top")

    # ── 底栏 ──
    ax.fill([0, width, width, 0], [0, 0, 60, 60], color=BG_CARD, alpha=0.4)
    ax.text(width / 2, 20, "数据仅供参考  ·  不构成投资建议",
            fontsize=10, color=TEXT_GREY, ha="center", va="center")

    # 保存
    output_dir.mkdir(parents=True, exist_ok=True)
    cover_path = output_dir / "cover.png"
    fig.savefig(cover_path, dpi=dpi, bbox_inches="tight", pad_inches=0,
                facecolor=BG_DARK, edgecolor="none")
    plt.close(fig)

    logger.info(f"封面图已生成 → {cover_path}")
    return cover_path


def generate_market_overview(
    snapshot,
    output_dir: Path,
) -> Optional[Path]:
    """
    生成行情总览图（900×700）：指数涨跌柱状图 + 行业板块强弱。

    Args:
        snapshot: 市场数据快照
        output_dir: 输出目录

    Returns:
        图表文件路径，数据不足时返回 None
    """
    indices = snapshot.index_changes
    extra = snapshot.extra
    top_sectors = extra.get("top_sectors", [])[:5] if extra else []
    bot_sectors = extra.get("bottom_sectors", [])[:3] if extra else []

    if not indices and not top_sectors:
        return None

    width, height = 900, 700
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, facecolor=BG_DARK)

    # ── 左上：指数涨跌柱状图 ──
    if indices:
        ax1 = fig.add_axes([0.06, 0.42, 0.55, 0.52])
        ax1.set_facecolor(BG_DARK)
        names = list(indices.keys())
        pcts = [v["pct"] for v in indices.values()]
        colors = [ACCENT_RED if p >= 0 else ACCENT_GREEN for p in pcts]

        bars = ax1.barh(names, pcts, color=colors, height=0.5)
        ax1.invert_yaxis()
        ax1.axvline(x=0, color=TEXT_GREY, linewidth=0.8, alpha=0.5)
        ax1.set_title("A 股主要指数 涨跌幅 %", fontsize=13, color=TEXT_WHITE, pad=10)
        ax1.tick_params(colors=TEXT_GREY, labelsize=11)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.spines["left"].set_color(TEXT_GREY)
        ax1.spines["bottom"].set_color(TEXT_GREY)
        ax1.xaxis.label.set_color(TEXT_GREY)
        ax1.yaxis.label.set_color(TEXT_GREY)

        for bar, pct in zip(bars, pcts):
            sign = "+" if pct >= 0 else ""
            ax1.text(pct + (0.15 if pct >= 0 else -0.15), bar.get_y() + bar.get_height() / 2,
                     f"{sign}{pct:.2f}%", ha="left" if pct >= 0 else "right",
                     va="center", fontsize=10, color=TEXT_WHITE)

    # ── 右上：利率 ──
    ax2 = fig.add_axes([0.64, 0.42, 0.32, 0.52])
    ax2.set_facecolor(BG_DARK)
    ax2.axis("off")

    y_r = 0.9
    ax2.text(0, y_r, "国债收益率", fontsize=13, color=TEXT_WHITE, fontweight="bold")
    cn_val = f"{snapshot.cn10y:.2f}%" if snapshot.cn10y else "--"
    us_val = f"{snapshot.us10y:.2f}%" if snapshot.us10y else "--"
    ax2.text(0, y_r - 0.12, f"CN 10Y", fontsize=11, color=TEXT_GREY)
    ax2.text(0.5, y_r - 0.12, cn_val, fontsize=18, color=TEXT_WHITE, fontweight="bold", ha="right")
    ax2.text(0, y_r - 0.28, f"US 10Y", fontsize=11, color=TEXT_GREY)
    ax2.text(0.5, y_r - 0.28, us_val, fontsize=18, color=TEXT_WHITE, fontweight="bold", ha="right")

    # 分隔线
    ax2.plot([0, 0.5], [y_r - 0.38, y_r - 0.38], color=TEXT_GREY, linewidth=0.5, alpha=0.4)

    # 北向资金
    north = snapshot.north_flow
    north_str = f"{north:.0f} 亿" if north else "未出库"
    ax2.text(0, y_r - 0.52, "北向资金", fontsize=11, color=TEXT_GREY)
    ax2.text(0.5, y_r - 0.52, north_str, fontsize=14, color=TEXT_WHITE, fontweight="bold", ha="right")

    # ── 下半部：行业板块 ──
    if top_sectors or bot_sectors:
        ax3 = fig.add_axes([0.06, 0.05, 0.90, 0.30])
        ax3.set_facecolor(BG_DARK)
        ax3.axis("off")

        # 领涨
        ax3.text(0, 0.95, "领涨板块", fontsize=13, color=TEXT_WHITE, fontweight="bold")
        y_pos = 0.70
        for s in top_sectors:
            pct = s["pct"]
            bar_w = min(abs(pct) / 8, 0.35)  # 归一化到 0-0.35
            ax3.add_patch(plt.Rectangle((0, y_pos), bar_w, 0.12,
                         color=ACCENT_RED, alpha=0.7))
            ax3.text(0.01, y_pos + 0.06, s["name"], fontsize=10, color=TEXT_WHITE, va="center")
            ax3.text(bar_w + 0.01, y_pos + 0.06, f"+{pct:.1f}%",
                     fontsize=10, color=ACCENT_RED, va="center", fontweight="bold")
            y_pos -= 0.17

        # 领跌
        ax3.text(0.50, 0.95, "领跌板块", fontsize=13, color=TEXT_WHITE, fontweight="bold")
        y_pos = 0.70
        for s in bot_sectors:
            pct = s["pct"]
            bar_w = min(abs(pct) / 8, 0.35)
            ax3.add_patch(plt.Rectangle((0.50 + 0.35 - bar_w, y_pos), bar_w, 0.12,
                         color=ACCENT_GREEN, alpha=0.7))
            ax3.text(0.51, y_pos + 0.06, s["name"], fontsize=10, color=TEXT_WHITE, va="center")
            ax3.text(0.50 + 0.35 - bar_w - 0.05, y_pos + 0.06, f"{pct:.1f}%",
                     fontsize=10, color=ACCENT_GREEN, va="center", fontweight="bold", ha="right")
            y_pos -= 0.17

    # 保存
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_path = output_dir / "market_overview.png"
    fig.savefig(chart_path, dpi=dpi, bbox_inches="tight", pad_inches=0.3,
                facecolor=BG_DARK, edgecolor="none")
    plt.close(fig)

    logger.info(f"行情总览图已生成 → {chart_path}")
    return chart_path


def _wrap_text(text: str, max_chars: int = 18, max_lines: int = 3) -> list:
    """简单折行，按 max_chars 断行，最多 max_lines 行"""
    lines = []
    remaining = text
    while remaining and len(lines) < max_lines:
        if len(remaining) <= max_chars:
            lines.append(remaining)
            break
        # 找断点
        cut = max_chars
        while cut > 0 and remaining[cut] not in " ，。、；：,.;: ":
            cut -= 1
        if cut == 0:
            cut = max_chars
        lines.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return lines[:max_lines]


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    from src.utils.models import DailySnapshot
    from pathlib import Path

    snap = DailySnapshot(
        date="2026-05-16",
        index_changes={
            "上证指数": {"close": 4135.39, "pct": -1.02},
            "深证成指": {"close": 15561.37, "pct": -1.17},
            "创业板指": {"close": 3929.06, "pct": -0.56},
            "科创50":   {"close": 1696.26, "pct": -1.67},
            "沪深300":  {"close": 4859.59, "pct": -1.12},
        },
        cn10y=1.7658,
        us10y=4.59,
        extra={
            "top_sectors": [
                {"name": "机器人",   "pct": 5.89},
                {"name": "氟化工",   "pct": 5.62},
                {"name": "家电",     "pct": 4.85},
                {"name": "自动化设备","pct": 3.74},
                {"name": "军工电子", "pct": 3.21},
            ],
        },
    )
    out = Path("/tmp/test_cover")
    path = generate_cover(snap, "美债承压+AI硬件回调，市场等待主线", out)
    print(f"Cover saved to {path}")
