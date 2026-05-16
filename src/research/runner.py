"""
FinSight 深度研报运行器。

流程：
  1. 从项目 .env 同步 API key 到 FinSight 的 .env
  2. 自动生成 my_config_auto.yaml
  3. subprocess 调 FinSight run_report.py（Python 3.11+ venv）
  4. 产物拷贝到 output/reports/YYYYMMDD_标的名/
  5. 推一条摘要到微信

用法：
    from src.research.runner import run_deep_research
    run_deep_research(stock_code="688008.SH")
"""

import os
import re
import shutil
import subprocess
import sys
import yaml
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

# 加载项目 .env
load_dotenv(ROOT / ".env")

FINSIGHT_DIR = ROOT / "vendor" / "finsight"
FINSIGHT_PYTHON = ROOT / "venv_finsight" / "bin" / "python3"

# ─── 美股常见 ticker 映射 ───
US_TICKER_MAP = {
    "NVDA": "NVDA", "AAPL": "AAPL", "MSFT": "MSFT", "GOOGL": "GOOGL",
    "AMZN": "AMZN", "META": "META", "TSLA": "TSLA", "AMD": "AMD",
    "INTC": "INTC", "ASML": "ASML", "TSM": "TSM", "BABA": "BABA",
    "NIO": "NIO", "XPEV": "XPEV", "LI": "LI", "BYD": "BYD",
}


def _sync_env():
    """
    从项目根 .env 读取 API key，写入 FinSight 的 .env。

    FinSight 的 run_report.py 通过 dotenv 加载 .env，
    变量名必须对齐它的 config yaml 里的 ${VAR_NAME} 引用。
    """
    env_path = FINSIGHT_DIR / ".env"

    # 1) LLM — DeepSeek 直连
    ds_key = os.getenv("DEEPSEEK_API_KEY", "")

    # 2) VLM — SiliconFlow
    sf_key = os.getenv("SILICONFLOW_API_KEY", "")
    if not sf_key:
        logger.warning(
            "SILICONFLOW_API_KEY 未在项目 .env 中设置。"
            "FinSight 的 VLM 图表审评（图表质量反馈）将无法工作。"
            "请前往 https://siliconflow.cn 注册免费账号，在项目 .env 中加上：\n"
            "  SILICONFLOW_API_KEY=sk-xxx\n"
            "  VLM 推荐模型：Qwen/Qwen2.5-VL-32B-Instruct"
        )

    # 3) Embedding — SiliconFlow
    emb_key = os.getenv("EMBEDDING_API_KEY", "")
    emb_model = os.getenv("EMBEDDING_MODEL_NAME", "")
    if not emb_key:
        # 降级：复用 SiliconFlow key
        if sf_key:
            emb_key = sf_key
            emb_model = "BAAI/bge-large-zh-v1.5"
            logger.info("EMBEDDING_API_KEY 未设置，复用 SILICONFLOW_API_KEY")
        else:
            logger.warning(
                "EMBEDDING_API_KEY 未设置且无 SILICONFLOW_API_KEY。"
                "FinSight 的报告嵌入/语义搜索功能将受限。"
            )

    # 4) Serper — 搜索
    serper_key = os.getenv("SERPER_API_KEY", "")
    if not serper_key:
        logger.warning(
            "SERPER_API_KEY 未在项目 .env 中设置。"
            "FinSight 的网络搜索功能将不可用，报告质量会下降。"
            "请前往 https://serper.dev 注册免费账号（2500 次/月），在项目 .env 中加上：\n"
            "  SERPER_API_KEY=xxx"
        )

    lines = [
        "# FinSight .env — 由 src/research/runner.py 自动生成",
        f"# 生成时间：{datetime.now().isoformat()}",
        "",
        "# LLM — DeepSeek 直连",
        "DS_MODEL_NAME=deepseek-v4-pro",
        f"DS_API_KEY={ds_key}",
        "DS_BASE_URL=https://api.deepseek.com",
        "",
        "# VLM — SiliconFlow 免费",
        "VLM_MODEL_NAME=Qwen/Qwen2.5-VL-32B-Instruct",
        f"VLM_API_KEY={sf_key}",
        "VLM_BASE_URL=https://api.siliconflow.cn/v1",
        "",
        "# Embedding — SiliconFlow 免费",
        f"EMBEDDING_MODEL_NAME={emb_model or 'BAAI/bge-large-zh-v1.5'}",
        f"EMBEDDING_API_KEY={emb_key}",
        "EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1",
        "",
        "# 搜索",
        f"SERPER_API_KEY={serper_key}",
        "",
    ]

    env_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"FinSight .env 已同步 → {env_path}")


def _build_config(
    target: str,
    target_type: str = "financial_company",
    output_dir: Optional[str] = None,
) -> Path:
    """
    根据目标自动生成 FinSight 的 my_config_auto.yaml。

    Args:
        target: 标的代码（如 688008.SH、NVDA）或主题名（如"储能"）
        target_type: financial_company / industry / macro / general
        output_dir: FinSight 输出目录（相对于 vendor/finsight）

    Returns:
        生成的 config yaml 文件路径
    """
    # 解析标的信息
    if target_type == "financial_company":
        ticker = target.upper()
        if ticker in US_TICKER_MAP or re.match(r"^[A-Z]{1,5}$", ticker):
            target_name = ticker
            stock_code = ticker
            language = "en"
            template = "src/template/company_outline_en.md"
        else:
            # A 股 → 尝试拉取名称
            target_name = _lookup_stock_name(ticker)
            stock_code = ticker
            language = "zh"
            template = "src/template/company_outline_zh.md"
    elif target_type == "industry":
        target_name = target
        stock_code = ""
        language = "zh"
        template = "src/template/company_outline_zh.md"
    elif target_type == "macro":
        target_name = target
        stock_code = ""
        language = "zh"
        template = "src/template/company_outline_zh.md"
    else:
        target_name = target
        stock_code = target
        language = "zh"
        template = "src/template/company_outline_zh.md"

    if output_dir is None:
        safe_name = re.sub(r"[^\w\-]", "_", target)
        output_dir = f"./outputs/{safe_name}"

    # 收集/分析任务
    if target_type == "financial_company":
        collect_tasks = [
            "资产负债表, 利润表, 现金流量表三大财务报表",
            "股票基本信息以及股价数据",
            "股东结构",
            "投资评级",
            "公司市销率, 净资产收益率(ROE), 市盈率, 市净率",
            "公司主要竞争对手情况",
        ]
        analysis_tasks = [
            "梳理公司发展历程、关键里程碑事件及当前核心主营业务范围",
            "分析公司产业链位置及竞争壁垒",
            "分析历年营收趋势、各业务板块占比变化及增长驱动因素",
            "评估公司盈利能力（ROE、毛利率、净利率）及运营效率",
            "进行同行业竞争对手对比分析，评估行业地位",
            "复盘近2年股价走势，分析关键事件对股价的影响",
            "预测未来两年核心财务数据，进行估值分析",
        ]
    elif target_type == "industry":
        collect_tasks = [
            f"{target}行业政策与市场规模数据",
            f"{target}行业主要上市公司及竞争格局",
            f"{target}行业技术路线与发展趋势",
            f"{target}相关指数数据",
        ]
        analysis_tasks = [
            f"梳理{target}行业发展历程及当前阶段",
            f"分析{target}行业竞争格局及龙头企业对比",
            f"评估{target}行业增长驱动因素及风险点",
            f"对{target}行业未来2-3年趋势做前瞻判断",
        ]
    elif target_type == "macro":
        collect_tasks = [
            f"{target}相关政策与历史事件",
            "宏观指标：GDP, CPI, PMI, 利率, 汇率",
            "主要经济体央行政策与市场预期",
            "相关资产表现：股指、债券、商品",
        ]
        analysis_tasks = [
            f"梳理{target}当前核心矛盾与市场共识",
            f"分析{target}对主要资产类别的影响路径",
            "进行历史类比分析，找出相似周期的市场表现",
            "对{target}未来走向给出情景分析",
        ]
    else:
        collect_tasks = [f"关于{target}的信息收集"]
        analysis_tasks = [f"关于{target}的分析"]

    config = {
        "target_name": target_name,
        "stock_code": stock_code,
        "target_type": target_type,
        "output_dir": output_dir,
        "language": language,
        "reference_doc_path": "src/template/report_template.docx",
        "outline_template_path": template,
        "custom_collect_tasks": collect_tasks,
        "custom_analysis_tasks": analysis_tasks,
        "use_collect_data_cache": True,
        "use_analysis_cache": True,
        "use_report_outline_cache": True,
        "use_full_report_cache": True,
        "use_post_process_cache": True,
        "llm_config_list": [
            {
                "model_name": "${DS_MODEL_NAME}",
                "api_key": "${DS_API_KEY}",
                "base_url": "${DS_BASE_URL}",
                "generation_params": {
                    "temperature": 0.7,
                    "max_tokens": 32768,
                    "top_p": 0.95,
                },
            },
            {
                "model_name": "${EMBEDDING_MODEL_NAME}",
                "api_key": "${EMBEDDING_API_KEY}",
                "base_url": "${EMBEDDING_BASE_URL}",
            },
            {
                "model_name": "${VLM_MODEL_NAME}",
                "api_key": "${VLM_API_KEY}",
                "base_url": "${VLM_BASE_URL}",
            },
        ],
    }

    config_path = FINSIGHT_DIR / "my_config_auto.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    logger.info(f"FinSight config 已生成 → {config_path}")
    return config_path


def _lookup_stock_name(stock_code: str) -> str:
    """尝试从新浪行情获取股票名称，失败则返回代码本身"""
    try:
        import requests
        code_num = stock_code.split(".")[0]
        mkt = "sh" if stock_code.endswith(".SH") else "sz"
        url = f"http://hq.sinajs.cn/list={mkt}{code_num}"
        resp = requests.get(
            url,
            headers={"Referer": "https://finance.sina.com.cn"},
            timeout=5,
        )
        resp.encoding = "gbk"
        parts = resp.text.split('"')[1].split(",")
        if len(parts) > 0 and parts[0]:
            return parts[0]
    except Exception:
        pass
    return stock_code


def _run_finsight(timeout_seconds: int = 3600) -> bool:
    """
    调用 FinSight run_report.py。

    使用 Python 3.11 venv，cwd 设到 FinSight 目录。
    超时默认 1 小时。

    Returns:
        True 表示成功，False 表示失败
    """
    if not FINSIGHT_PYTHON.exists():
        logger.error(f"FinSight venv 不存在：{FINSIGHT_PYTHON}")
        logger.error("请先创建 Python 3.11+ venv：")
        logger.error(f"  ~/.pyenv/versions/3.11.11/bin/python3 -m venv {FINSIGHT_PYTHON.parent}")
        return False

    logger.info("启动 FinSight 深度研报生成...")
    logger.info("（预计 20-40 分钟，请耐心等待）")

    try:
        result = subprocess.run(
            [str(FINSIGHT_PYTHON), "run_report.py"],
            cwd=str(FINSIGHT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        # 打印关键日志
        for line in result.stdout.split("\n"):
            if any(kw in line for kw in ["INFO", "ERROR", "WARNING", "完成", "finished", "error"]):
                logger.info(f"[FinSight] {line.strip()[:200]}")

        if result.stderr:
            stderr_lines = result.stderr.strip().split("\n")
            # 只打印有意义的错误行
            for line in stderr_lines[-20:]:
                if line.strip():
                    logger.warning(f"[FinSight stderr] {line.strip()[:200]}")

        if result.returncode != 0:
            logger.error(f"FinSight 退出码非零：{result.returncode}")
            return False

        logger.info("FinSight 运行完成")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"FinSight 运行超时（>{timeout_seconds}s），已终止")
        return False
    except Exception as e:
        logger.error(f"FinSight 运行异常：{e}")
        return False


def _copy_output(config_path: Path, target: str) -> Optional[Path]:
    """
    将 FinSight 输出产物拷贝到项目 output/reports/ 下。

    Returns:
        目标目录路径，无产物时返回 None
    """
    # 从 config yaml 读取 output_dir
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    finsight_out = FINSIGHT_DIR / cfg.get("output_dir", "./outputs").lstrip("./")

    if not finsight_out.exists():
        logger.warning(f"FinSight 输出目录不存在：{finsight_out}")
        return None

    # 目标目录
    today = date.today().isoformat()
    safe_name = re.sub(r"[^\w\-]", "_", target)
    dest_dir = ROOT / "output" / "reports" / f"{today}_{safe_name}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # 拷贝所有文件
    file_count = 0
    for src_file in finsight_out.rglob("*"):
        if src_file.is_file():
            rel = src_file.relative_to(finsight_out)
            dst_file = dest_dir / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            file_count += 1

    logger.info(f"产物已拷贝：{file_count} 个文件 → {dest_dir}")
    return dest_dir


def _notify(target: str, dest_dir: Optional[Path], success: bool, elapsed_s: float):
    """通过 Server 酱推送一条 FinSight 完成通知"""
    try:
        from src.publishers.serverchan import push

        if success and dest_dir:
            # 统计产物
            files = list(dest_dir.rglob("*"))
            pdfs = [f for f in files if f.suffix == ".pdf"]
            docxs = [f for f in files if f.suffix == ".docx"]
            title = f"📄 FinSight 研报完成 - {target}"
            content = (
                f"标的：{target}\n"
                f"耗时：{elapsed_s/60:.0f} 分钟\n"
                f"产物：{len(files)} 个文件"
            )
            if pdfs:
                content += f"（PDF {len(pdfs)} 份）"
            if docxs:
                content += f"（DOCX {len(docxs)} 份）"
            content += f"\n位置：{dest_dir}"
        else:
            title = f"❌ FinSight 研报失败 - {target}"
            content = f"标的：{target}\n耗时：{elapsed_s/60:.0f} 分钟后失败\n请查看日志 logs/main.log"

        push(title=title, content=content)
        logger.info("FinSight 完成通知已推送到微信")
    except Exception as e:
        logger.warning(f"FinSight 完成通知推送失败：{e}")


def run_deep_research(
    target: str,
    target_type: str = "financial_company",
    timeout_seconds: int = 3600,
) -> bool:
    """
    执行一次 FinSight 深度研报。

    Args:
        target: 标的代码或主题名
        target_type: financial_company / industry / macro
        timeout_seconds: 超时秒数，默认 3600（1 小时）

    Returns:
        True 表示成功
    """
    t0 = datetime.now()

    logger.info(f"===== FinSight 深度研报：{target}（类型={target_type}）=====")

    # 1) 同步环境
    _sync_env()

    # 2) 生成配置
    config_path = _build_config(target, target_type)
    logger.info(f"Config path: {config_path}")

    # 3) 运行 FinSight
    success = _run_finsight(timeout_seconds)

    # 4) 拷贝产物
    dest_dir = _copy_output(config_path, target) if success else None

    # 5) 推送通知
    elapsed = (datetime.now() - t0).total_seconds()
    _notify(target, dest_dir, success, elapsed)

    logger.info(f"===== FinSight 深度研报完成（{elapsed/60:.1f} 分钟）=====")
    return success


# ─── 快速测试 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "688008.SH"
    run_deep_research(target)
