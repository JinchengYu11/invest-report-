"""
Dexter 桥接层 — 通过子进程调用 TypeScript 实现的 Dexter 金融研究 Agent。

流程：
  1. 检查 vendor/dexter/ 是否已 clone
  2. 从 .env 加载 DEEPSEEK_API_KEY
  3. 可选：调用 wind_tools.enrich_question() 附加 A 股数据
  4. subprocess → bun run ask.ts "问题"
  5. 返回答案文本

用法：
    from src.qa.bridge import ask_dexter
    answer = ask_dexter("今天A股科技板块怎么样？")
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# 加载项目 .env
load_dotenv(ROOT / ".env")

DEXTER_DIR = ROOT / "vendor" / "dexter"
ASK_SCRIPT = DEXTER_DIR / "ask.ts"


ASK_TS_CONTENT = r"""#!/usr/bin/env bun
/**
 * Dexter 单问封装 — 供 Python 子进程调用（由 bridge.py 自动生成）。
 *
 * 环境变量：
 *   DEEPSEEK_API_KEY — 由 bridge.py 从 .env 注入
 *   DEXTER_MODEL      — 可选，默认 deepseek-v4-pro
 */

import { Agent } from "./src/agent/agent.js";

const question = process.argv[2];
if (!question) {
  console.error("用法：bun run ask.ts \"你的金融问题\"");
  process.exit(1);
}

const model = process.env.DEXTER_MODEL || "deepseek-v4-pro";

const agent = await Agent.create({
  model,
  maxIterations: 8,
});

let finalAnswer = "";

for await (const event of agent.run(question)) {
  if (event.type === "done") {
    finalAnswer = event.answer;
  }
}

if (!finalAnswer) {
  console.error("Dexter 未返回答案");
  process.exit(1);
}

console.log(finalAnswer);
"""


def _ensure_dexter_installed():
    """检查 Dexter 是否已 clone 到 vendor/，并自动创建 ask.ts"""
    if not DEXTER_DIR.exists():
        raise FileNotFoundError(
            f"Dexter 目录不存在：{DEXTER_DIR}\n\n"
            "请先 clone Dexter：\n"
            "  mkdir -p vendor && cd vendor && git clone https://github.com/virattt/dexter.git\n"
            "  cd dexter && bun install && cp env.example .env"
        )

    if not (DEXTER_DIR / "node_modules").exists():
        raise FileNotFoundError(
            f"Dexter 依赖未安装\n\n"
            "请在 vendor/dexter/ 下运行：\n"
            "  bun install"
        )

    # 自动创建 ask.ts
    if not ASK_SCRIPT.exists():
        ASK_SCRIPT.write_text(ASK_TS_CONTENT, encoding="utf-8")
        logger.info(f"已自动创建 {ASK_SCRIPT}")


def ask_dexter(
    question: str,
    *,
    enrich_with_market: bool = True,
    model: Optional[str] = None,
    timeout_seconds: int = 300,
) -> str:
    """
    向 Dexter 提问，返回答案。

    Args:
        question: 用户问题
        enrich_with_market: 是否注入 A 股行情上下文
        model: 模型名，默认从 DEXTER_MODEL 或 deepseek-v4-pro
        timeout_seconds: 超时秒数

    Returns:
        Dexter 的答案文本

    Raises:
        FileNotFoundError: vendor/dexter/ 未 clone
        subprocess.TimeoutExpired: 超时
        RuntimeError: Dexter 返回错误
    """
    _ensure_dexter_installed()

    # 可选：附加上下文
    if enrich_with_market:
        try:
            from src.qa.wind_tools import enrich_question
            question = enrich_question(question)
        except Exception as e:
            logger.warning(f"A 股数据增强失败：{e}")

    # 准备环境变量
    env = os.environ.copy()
    env["DEEPSEEK_API_KEY"] = os.getenv("DEEPSEEK_API_KEY", "")
    if not env["DEEPSEEK_API_KEY"]:
        raise RuntimeError("DEEPSEEK_API_KEY 未在 .env 中设置")

    if model:
        env["DEXTER_MODEL"] = model

    logger.info(f"调用 Dexter，问题长度 {len(question)} 字符...")

    # 调用 ask.ts
    result = subprocess.run(
        ["bun", "run", str(ASK_SCRIPT), question],
        cwd=str(DEXTER_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error(f"Dexter 返回非零退出码：{result.returncode}")
        if stderr:
            logger.error(stderr)
        raise RuntimeError(f"Dexter 执行失败：{stderr}")

    answer = result.stdout.strip()
    if not answer:
        raise RuntimeError("Dexter 返回空答案")

    logger.info(f"Dexter 回答长度：{len(answer)} 字符")
    return answer


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        ans = ask_dexter("一句话介绍今天A股的情况", timeout_seconds=60)
        print(ans)
    except FileNotFoundError as e:
        print(f"[跳过] {e}")
    except Exception as e:
        print(f"[错误] {e}")
