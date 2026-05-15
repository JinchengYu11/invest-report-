"""
Wind 终端数据采集器。

通过 WindPy 获取每日行情快照（指数、北向资金、利率）。
Wind 终端未登录时降级返回 None，不影响新闻采集和简报生成。
"""

from datetime import date
from typing import Optional

from loguru import logger

from src.utils.models import DailySnapshot


def fetch_daily_snapshot(run_date: Optional[date] = None) -> Optional[DailySnapshot]:
    """
    从 Wind 终端拉取每日市场数据快照。

    Args:
        run_date: 查询日期，None 则今天

    Returns:
        DailySnapshot 对象，Wind 不可用时返回 None（上游需处理降级）
    """
    if run_date is None:
        run_date = date.today()

    date_str = run_date.strftime("%Y-%m-%d")

    try:
        from WindPy import w  # noqa: F401

        w.start()
        if not w.isconnected():
            logger.warning("Wind 终端未连接，跳过行情数据")
            return None
    except ImportError:
        logger.warning("WindPy 未安装，跳过行情数据（调试时可忽略）")
        return None
    except Exception as e:
        logger.warning(f"WindPy 初始化异常：{e}")
        return None

    # TODO: 实现具体指标拉取 —— 指数涨跌、北向净流入、中美国债收益率
    # 当前返回空快照占位，保证主流程能跑通
    logger.info(f"Wind 行情数据采集完成（指标拉取待实现）")
    return DailySnapshot(date=date_str)
