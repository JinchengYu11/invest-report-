"""
Server 酱微信推送。

申请：https://sct.ftqq.com 扫码绑微信，得到 SCT 开头的 key
环境变量：SERVERCHAN_KEY
"""

import os
from typing import Optional

import requests
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=15))
def push(title: str, content: str, short: Optional[str] = None) -> bool:
    """
    推送一条消息到微信。

    Args:
        title: 标题（微信看到的）
        content: 正文，支持 Markdown
        short: 卡片预览文字（可选）

    Returns:
        是否成功
    """
    key = os.getenv("SERVERCHAN_KEY")
    if not key:
        logger.warning("SERVERCHAN_KEY 未设置，跳过推送")
        return False

    url = f"https://sctapi.ftqq.com/{key}.send"
    payload = {
        "title": title,
        "desp": content,
    }
    if short:
        payload["short"] = short

    try:
        resp = requests.post(url, data=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) == 0:
            logger.info(f"推送成功：{title}")
            return True
        else:
            logger.error(f"推送失败：{data}")
            return False
    except Exception as e:
        logger.error(f"推送异常：{e}")
        raise


# ───── 测试 ─────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    push(
        title="测试推送",
        content="## 这是一条测试\n\n如果你看到这条消息，说明 Server 酱配置成功。",
    )
