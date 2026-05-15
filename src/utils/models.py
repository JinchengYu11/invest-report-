"""
统一的新闻数据模型。
所有采集器返回的新闻都用 NewsItem 表示。
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """单条新闻"""

    title: str                              # 标题
    content: str = ""                       # 正文（可能为空，看源是否提供）
    url: str = ""                           # 原文链接
    source: str                             # 来源名（财联社、华尔街见闻 等）
    published_at: datetime                  # 发布时间
    sector: Optional[str] = None            # 归属板块（采集时未知，过滤阶段填充）
    importance: int = 0                     # 重要性 0-3，过滤阶段或 AI 阶段打分
    tags: List[str] = Field(default_factory=list)

    def short_repr(self) -> str:
        """用于日志/调试的紧凑字符串"""
        return f"[{self.source}] {self.title[:40]}"


class DailySnapshot(BaseModel):
    """每日市场数据快照（Wind 拉取的结果）"""

    date: str                               # YYYY-MM-DD
    index_changes: dict = Field(default_factory=dict)
    # e.g. {"上证综指": {"close": 3200.5, "pct": 0.5}, ...}
    north_flow: Optional[float] = None      # 北向净流入（亿元）
    cn10y: Optional[float] = None           # 中国 10Y 国债收益率（%）
    cn10y_change_bp: Optional[float] = None
    us10y: Optional[float] = None
    us10y_change_bp: Optional[float] = None
    extra: dict = Field(default_factory=dict)


class DraftPackage(BaseModel):
    """最终输出的小红书草稿包"""

    date: str
    title: str
    body_markdown: str                      # 正文（小红书可直接复制）
    hashtags: List[str] = Field(default_factory=list)
    cover_image_path: Optional[str] = None  # 封面图本地路径
    chart_paths: List[str] = Field(default_factory=list)
