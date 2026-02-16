"""
Phase3 FinancialMaster 動作確認用スクリプト。
main.py に影響を与えない。プロジェクトルートから実行すること。

使用例:
    python scripts/test_financial_master.py
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from parser.xbrl_parser import XBRLParser
from parser.context_resolver import ContextResolver
from normalizer.fact_normalizer import FactNormalizer
from financial.financial_master import FinancialMaster

if __name__ == "__main__":
    xbrl_path = project_root / "data/edinet/raw_xbrl/2025/S100W67S/jpcrp030000-asr-001_E05325-000_2025-03-31_01_2025-06-25.xbrl"

    if not xbrl_path.exists():
        print("XBRLファイルが見つかりません:", xbrl_path)
        sys.exit(1)

    parser = XBRLParser(xbrl_path)
    parsed_data = parser.parse()
    resolver = ContextResolver(parser.root)
    context_map = resolver.build_context_map()
    normalizer = FactNormalizer(parsed_data, context_map)
    normalized_data = normalizer.normalize()

    master = FinancialMaster(normalized_data)
    result = master.compute()

    print("=" * 60)
    print("FinancialMaster 出力")
    print("=" * 60)
    print("doc_id:", result["doc_id"])

    m = result["current_year"]["metrics"]
    print("\n--- 収益性 ---")
    print("ROE:", m.get("roe"))
    print("ROA:", m.get("roa"))
    print("Operating Margin:", m.get("operating_margin"))
    print("Net Margin:", m.get("net_margin"))

    print("\n--- 財務安全性 ---")
    print("Equity Ratio:", m.get("equity_ratio"))
    print("D/E Ratio:", m.get("de_ratio"))

    print("\n--- キャッシュフロー ---")
    print("Free Cash Flow:", m.get("free_cash_flow"))

    print("\n--- 成長率 ---")
    print("Sales Growth:", m.get("sales_growth"))
    print("Profit Growth:", m.get("profit_growth"))
    print("EPS Growth:", m.get("eps_growth"))

    print("\n--- 参考（当期） ---")
    print("Equity (resolved):", m.get("equity"))
    print("Interest Bearing Debt (resolved):", m.get("interest_bearing_debt"))
