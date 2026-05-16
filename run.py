#!/usr/bin/env python3
"""
invest_brief 统一入口。

用法：
  python run.py daily                    → 跑每日投资简报（调用 src/main.py）
  python run.py ask "今天AI板块怎么看？"  → 调 Dexter 做即时金融研究
  python run.py report 688008.SH         → 个股快速报告（Dexter）
  python run.py deep 688008.SH           → 深度研报（FinSight，2 万字+）
"""

import argparse
import os
import re
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
    """个股深度分析 → 生成报告 + 保存文件 + 推微信"""
    from src.qa.report import generate_report, _fetch_stock_quote

    stock_code = args.stock.upper()
    if "." not in stock_code:
        if stock_code.startswith(("688", "600", "601", "603", "605")):
            stock_code += ".SH"
        else:
            stock_code += ".SZ"

    # 获取股票简称
    try:
        quote = _fetch_stock_quote(stock_code)
        stock_name = quote["name"]
    except Exception:
        stock_name = stock_code

    print(f"📄 生成 {stock_name}（{stock_code}）深度分析报告...")
    print("   （约需 2-5 分钟）")
    print()

    try:
        report = generate_report(stock_code, timeout_seconds=args.timeout)
    except FileNotFoundError as e:
        print(f"\n❌ {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 报告生成失败：{e}")
        sys.exit(1)

    # 保存到文件
    from datetime import date
    report_dir = ROOT / "output" / "reports" / stock_code.split(".")[0]
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{date.today().isoformat()}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n📁 已保存：{report_path}")

    # 推送微信
    if not args.no_push:
        try:
            from src.publishers.serverchan import push
            # Server 酱有长度限制，标题用报告摘要，正文推送
            first_line = report.split("\n")[0].lstrip("#").strip()[:80]
            push(
                title=f"📄 {stock_name} 深度报告 - {date.today().isoformat()}",
                content=report,
            )
            print("📲 已推送到微信")
        except Exception as e:
            print(f"⚠️ 微信推送失败：{e}")


def main():
    parser = argparse.ArgumentParser(
        description="invest_brief — 个人投资研究助理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python run.py daily                       跑每日简报
  python run.py daily --dry-run             只生成不推送
  python run.py ask "今天A股怎么看？"        即时问答
  python run.py report 688008.SH            快速报告（Dexter，2-5 分钟）
  python run.py deep 688008.SH              深度研报（FinSight，20-40 分钟）
  python run.py deep --type industry 储能    行业研报
  python run.py deep --type macro 美联储利率  宏观研报
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
    p_report = sub.add_parser("report", help="个股快速分析（Dexter）")
    p_report.add_argument("stock", type=str, help="股票代码，如 688008.SH")
    p_report.add_argument("--timeout", type=int, default=600, help="超时秒数（默认 600）")
    p_report.add_argument("--no-push", action="store_true", help="不推送到微信")

    # deep
    p_deep = sub.add_parser("deep", help="深度研报（FinSight，2 万字+）")
    p_deep.add_argument("target", type=str, help="股票代码 / 行业名 / 宏观主题")
    p_deep.add_argument(
        "--type", type=str, default="financial_company",
        choices=["financial_company", "industry", "macro"],
        help="研报类型（默认 financial_company）",
    )
    p_deep.add_argument("--timeout", type=int, default=3600, help="超时秒数（默认 3600 = 1 小时）")

    args = parser.parse_args()

    if args.command == "daily":
        cmd_daily(args)
    elif args.command == "ask":
        cmd_ask(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "deep":
        cmd_deep(args)
    else:
        parser.print_help()


def cmd_deep(args):
    """FinSight 深度研报"""
    from src.research.runner import run_deep_research

    target = args.target.strip()
    target_type = args.type or "financial_company"

    # 自动识别美股 ticker（纯英文字母）
    if target_type == "financial_company" and not re.search(r"[一-鿿]", target):
        if re.match(r"^[A-Za-z]{1,5}$", target):
            target = target.upper()

    type_labels = {
        "financial_company": f"📊 个股深度研报：{target}",
        "industry": f"🏭 行业深度研报：{target}",
        "macro": f"🌐 宏观深度研报：{target}",
    }
    print(type_labels.get(target_type, f"📄 深度研报：{target}"))
    print("   （FinSight 运行约需 20-40 分钟，可加 --timeout 调整）")
    print()

    try:
        success = run_deep_research(
            target=target,
            target_type=target_type,
            timeout_seconds=args.timeout,
        )
        if success:
            print("\n✅ FinSight 研报完成")
        else:
            print("\n❌ FinSight 研报失败，请查看日志")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ 运行异常：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
