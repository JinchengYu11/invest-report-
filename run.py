#!/usr/bin/env python3
"""
invest_brief 统一入口。

用法：
  python run.py daily                    → 跑每日投资简报（调用 src/main.py）
  python run.py ask "今天AI板块怎么看？"  → 调 Dexter 做即时金融研究
  python run.py report 300750.SZ         → 个股深度分析（FinSight，后续实现）
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def cmd_daily(args):
    """跑每日简报"""
    main_py = ROOT / "src" / "main.py"
    env = os.environ.copy()
    if args.dry_run:
        env["DRY_RUN"] = "true"

    print(f"📊 运行每日简报...")
    result = subprocess.run(
        [sys.executable, str(main_py)],
        cwd=str(ROOT),
        env=env,
    )
    sys.exit(result.returncode)


def cmd_ask(args):
    """Dexter 金融问答"""
    from src.qa.bridge import ask_dexter

    question = args.question
    print(f"🔍 向 Dexter 提问：{question}\n")
    print("思考中...\n")

    try:
        answer = ask_dexter(
            question,
            enrich_with_market=not args.no_market,
            timeout_seconds=args.timeout,
        )
        print("\n" + "=" * 60)
        print(answer)
        print("=" * 60)
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 出错了：{e}")
        sys.exit(1)


def cmd_report(args):
    """个股深度分析"""
    from src.qa.report import generate_report

    stock_code = args.stock.upper()
    if "." not in stock_code:
        # 纯数字 → 尝试补后缀
        if stock_code.startswith(("688", "600", "601", "603", "605")):
            stock_code += ".SH"
        else:
            stock_code += ".SZ"

    print(f"📄 生成 {stock_code} 深度分析报告...")
    print("   （约需 2-5 分钟，可加 --timeout 调整）")
    print()

    try:
        report = generate_report(stock_code, timeout_seconds=args.timeout)
        print()
        print("=" * 60)
        print(report)
        print("=" * 60)
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 报告生成失败：{e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="invest_brief — 个人投资研究助理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python run.py daily                    跑每日简报
  python run.py daily --dry-run          只生成不推送
  python run.py ask "今天A股怎么看？"     即时问答
  python run.py report 300750.SZ         个股深度（后续）
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # daily
    p_daily = sub.add_parser("daily", help="跑每日投资简报")
    p_daily.add_argument("--dry-run", action="store_true", help="只生成不推送")

    # ask
    p_ask = sub.add_parser("ask", help="Dexter 即时金融问答")
    p_ask.add_argument("question", type=str, help="你的金融问题")
    p_ask.add_argument("--no-market", action="store_true", help="不附加 A 股行情上下文")
    p_ask.add_argument("--timeout", type=int, default=600, help="超时秒数（默认 600）")

    # report
    p_report = sub.add_parser("report", help="个股深度分析")
    p_report.add_argument("stock", type=str, help="股票代码，如 688008.SH")
    p_report.add_argument("--timeout", type=int, default=600, help="超时秒数（默认 600）")

    args = parser.parse_args()

    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "report":
        cmd_report(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
