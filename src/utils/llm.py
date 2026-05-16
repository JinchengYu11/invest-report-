"""
DeepSeek V4 Pro 客户端封装。

文档：https://api-docs.deepseek.com/
模型：deepseek-v4-pro（Thinking / Non-Thinking 双模式，1M 上下文）

用法：
    from src.utils.llm import LLMClient
    client = LLMClient()
    text = client.chat([
        {"role": "system", "content": "你是一个投资研究助理"},
        {"role": "user", "content": "今天有这些新闻：..."},
    ])
"""

import os
import time
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMClient:
    """DeepSeek 调用封装，带重试和日志"""

    def __init__(self, config_path: Optional[str] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"

        with open(config_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f)
        llm_cfg = settings["llm"]

        self.model = llm_cfg["model"]
        self.temperature = llm_cfg["temperature"]
        self.max_tokens = llm_cfg["max_tokens"]
        self.thinking_enabled = llm_cfg["thinking_enabled"]
        self.reasoning_effort = llm_cfg["reasoning_effort"]
        self.timeout = llm_cfg["timeout_seconds"]
        self.max_retries = llm_cfg["max_retries"]

        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("环境变量 DEEPSEEK_API_KEY 未设置")

        self.client = OpenAI(
            api_key=api_key,
            base_url=llm_cfg["base_url"],
            timeout=self.timeout,
            max_retries=0,  # 由 tenacity 统一控制重试，避免双重重试
        )

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=3, max=60))
    def chat(
        self,
        messages: list,
        thinking: Optional[bool] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        调用 chat completion。

        Args:
            messages: 消息列表，OpenAI 格式
            thinking: 是否启用 thinking 模式，None 则用配置默认值
            temperature: 覆盖默认 temperature

        Returns:
            模型返回的文本
        """
        use_thinking = thinking if thinking is not None else self.thinking_enabled
        temp = temperature if temperature is not None else self.temperature

        t0 = time.time()
        logger.debug(f"调用 LLM，thinking={use_thinking}, temp={temp}")

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if use_thinking:
            kwargs["reasoning_effort"] = self.reasoning_effort
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = self.client.chat.completions.create(**kwargs)

        text = response.choices[0].message.content
        elapsed = time.time() - t0
        usage = response.usage
        logger.info(
            f"LLM 完成 | {elapsed:.1f}s | "
            f"in={usage.prompt_tokens} out={usage.completion_tokens}"
        )
        return text


# ───── 快速测试 ─────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    client = LLMClient()
    reply = client.chat(
        [{"role": "user", "content": "用一句话解释美联储降息对 A 股的影响。"}],
        thinking=False,
    )
    print(reply)
