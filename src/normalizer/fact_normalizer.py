"""
FactNormalizer
事実の正規化専用レイヤー。タグ→標準キー変換・current/prior分類・型変換・連結優先のみ。
補完・再構成・推測は行わず、FinancialMasterで処理する。
"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PL（duration）: タグ部分一致 -> 出力キー（数値はint）
# 同一キーは先頭が優先（first-match-wins）。具体的なタグを先に配置。
# ---------------------------------------------------------------------------
PL_TAGS = [
    # net_sales: SummaryOfBusinessResults を優先、本表を後続フォールバック
    ("NetSalesSummaryOfBusinessResults", "net_sales"),
    ("RevenueIFRSSummaryOfBusinessResults", "net_sales"),
    ("NetSales", "net_sales"),
    ("OperatingRevenue1SummaryOfBusinessResults", "net_sales"),
    ("OperatingRevenue2SummaryOfBusinessResults", "net_sales"),
    # operating_income
    ("OperatingIncome", "operating_income"),
    ("OperatingProfitLoss", "operating_income"),
    # ordinary_income: JGAAP特有（IFRSには概念なし）
    ("OrdinaryIncomeSummaryOfBusinessResults", "ordinary_income"),
    ("OrdinaryIncomeLossSummaryOfBusinessResults", "ordinary_income"),
    ("OrdinaryIncome", "ordinary_income"),
    # net_income_attributable_to_parent
    ("ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults", "profit_loss"),
    ("ProfitLossAttributableToOwnersOfParentIFRSSummaryOfBusinessResults", "profit_loss"),
    ("ProfitLossAttributableToOwnersOfParent", "profit_loss"),
]

# ---------------------------------------------------------------------------
# BS（instant）: タグ部分一致 -> 出力キー
# 同一キーは先頭が優先（first-match-wins）。
# ---------------------------------------------------------------------------
BS_TAGS = [
    # total_assets: "TotalAssets" はAssets系の誤マッチを防ぐ
    ("TotalAssetsSummaryOfBusinessResults", "total_assets"),
    ("TotalAssetsIFRSSummaryOfBusinessResults", "total_assets"),
    ("TotalAssets", "total_assets"),
    # equity 関連（FinancialMaster で優先順位解決）
    ("ShareholdersEquity", "shareholders_equity"),
    ("EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults", "equity_attributable_to_owners"),
    ("EquityAttributableToOwnersOfParent", "equity_attributable_to_owners"),
    ("NetAssetsSummaryOfBusinessResults", "net_assets"),
    ("NetAssets", "net_assets"),
    # total_number_of_issued_shares
    ("TotalNumberOfIssuedSharesSummaryOfBusinessResults", "total_number_of_issued_shares"),
    ("IssuedSharesTotalNumberOfSharesEtc", "total_number_of_issued_shares"),
    ("NumberOfIssuedSharesAsOfFilingDateTotalNumberOfSharesEtc", "total_number_of_issued_shares"),
    # cash_and_equivalents（CF期末残高 or BS）
    ("CashAndCashEquivalentsSummaryOfBusinessResults", "cash_and_equivalents"),
    ("CashAndCashEquivalentsIFRSSummaryOfBusinessResults", "cash_and_equivalents"),
    ("CashAndCashEquivalents", "cash_and_equivalents"),
    ("CashAndDeposits", "cash_and_deposits"),
    # 有利子負債構成項目（JGAAP）
    ("ShortTermBorrowings", "short_term_borrowings"),
    ("CurrentPortionOfLongTermBorrowings", "current_portion_of_long_term_borrowings"),
    ("CommercialPapers", "commercial_papers"),
    ("CurrentPortionOfBonds", "current_portion_of_bonds"),
    ("BondsPayable", "bonds_payable"),
    ("LongTermBorrowings", "long_term_borrowings"),
    # リース債務: CL=流動、NCL=固定、汎用LeaseObligations
    ("LeaseObligationsCL", "short_term_lease_obligations"),
    ("ShortTermLeaseObligations", "short_term_lease_obligations"),
    ("LeaseObligationsNCL", "long_term_lease_obligations"),
    ("LongTermLeaseObligations", "long_term_lease_obligations"),
    ("LeaseObligations", "lease_obligations"),
    # 有利子負債構成項目（IFRS）
    ("CurrentBorrowings", "short_term_borrowings"),
    ("NoncurrentBorrowings", "long_term_borrowings"),
    ("CurrentLeaseLiabilities", "short_term_lease_obligations"),
    ("NoncurrentLeaseLiabilities", "long_term_lease_obligations"),
]

# ---------------------------------------------------------------------------
# CF（duration）: タグ部分一致 -> 出力キー
# 同一キーは先頭が優先（first-match-wins）。
# ---------------------------------------------------------------------------
CF_TAGS = [
    # operating_cash_flow: Summary を優先
    ("NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults", "operating_cash_flow"),
    ("CashFlowsFromUsedInOperatingActivitiesIFRSSummaryOfBusinessResults", "operating_cash_flow"),
    ("NetCashProvidedByUsedInOperatingActivities", "operating_cash_flow"),
    ("CashFlowsFromUsedInOperatingActivities", "operating_cash_flow"),
    # investing / financing
    ("NetCashProvidedByUsedInInvestingActivities", "net_cash_used_in_investing_activities"),
    ("NetCashProvidedByUsedInFinancingActivities", "net_cash_provided_by_financing_activities"),
    # depreciation（EBITDA算出用）: CF表の減価償却費を優先
    ("DepreciationAndAmortizationOpeCF", "depreciation"),
    ("DepreciationAndAmortisationExpense", "depreciation"),
    ("DepreciationSGA", "depreciation"),
]

# ---------------------------------------------------------------------------
# 非財務情報（duration）: 配当（個別ベースからも取得）
# ---------------------------------------------------------------------------
DIVIDEND_TAGS = [
    ("DividendPaidPerShareSummaryOfBusinessResults", "dividends_per_share"),
]

# ---------------------------------------------------------------------------
# DEI（非数値）: タグ部分一致 -> 出力キー
# ---------------------------------------------------------------------------
DEI_TAGS = [
    ("SecurityCodeDEI", "security_code"),
    ("CompanyName", "company_name"),
    ("AccountingStandardsDEI", "accounting_standard"),
    ("WhetherConsolidatedFinancialStatementsArePrepared", "is_consolidated_dei"),
    ("CurrentPeriodEndDateDEI", "current_period_end_date"),
    ("CurrentFiscalYearEndDateDEI", "current_fiscal_year_end_date"),
]


def _current_and_prior_year_ends(context_map: dict[str, dict[str, Any]]) -> tuple[str | None, str | None]:
    """context_mapからcurrent_year_end, prior_year_endを算出（durationのend_dateのみ対象）。"""
    end_dates: list[str] = []
    for ctx in context_map.values():
        if ctx.get("type") == "duration" and ctx.get("end_date"):
            end_dates.append(ctx["end_date"])
    if not end_dates:
        return None, None
    sorted_dates = sorted(set(end_dates), reverse=True)
    current_year_end = sorted_dates[0]
    prior_year_end = None
    try:
        current_dt = datetime.strptime(current_year_end, "%Y-%m-%d")
        prior_dt = current_dt.replace(year=current_dt.year - 1)
        for d in sorted_dates:
            try:
                if datetime.strptime(d, "%Y-%m-%d").year == prior_dt.year:
                    prior_year_end = d
                    break
            except ValueError:
                continue
    except ValueError:
        logger.warning("日付解析失敗: %s", current_year_end)
    return current_year_end, prior_year_end


def _tag_matches(tag: str, keyword: str) -> bool:
    """タグがキーワードを部分一致で含むか。ローカル名で判定（prefix:local の local 部分）。"""
    local = tag.split(":")[-1] if ":" in tag else tag
    return keyword in local


def _is_consolidated_context(context_ref: str) -> bool:
    """contextRefが連結か。NonConsolidatedを含む場合は単体。"""
    return "NonConsolidated" not in context_ref


def _has_member_dimension(context_ref: str) -> bool:
    """contextRefにセグメント・メンバーdimensionが含まれるか。
    セグメント情報（ReportableSegmentsMember等）の値を除外するために使用。
    ただし NonConsolidatedMember は連結/単体区分なので除外しない。
    """
    if "Member" not in context_ref:
        return False
    if context_ref.endswith("_NonConsolidatedMember"):
        return False
    parts = context_ref.split("_")
    for part in parts[1:]:
        if "Member" in part and part != "NonConsolidatedMember":
            return True
    return False


def _parse_numeric_value(value: str) -> int | None:
    """
    文字列を数値に変換する。単位変換は行わない。

    XBRLのdecimals属性は精度を示すもので単位変換には使わない（XBRL仕様）。
    単位はunitRefが指すunit定義で決まる。EDINETの主要財務指標は円単位で統一されているため、
    値をそのまま使用する。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(value.strip())
    except (ValueError, TypeError):
        return None


def _parse_float_value(value: str) -> float | None:
    """文字列をfloatに変換する。配当等の小数値用。単位変換は行わない。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return None


def _parse_consolidated_dei(value: str) -> bool:
    """WhetherConsolidatedの値をboolに。"""
    if value is None:
        return False
    v = str(value).strip().lower()
    if v in ("true", "1", "yes", "有"):
        return True
    return False


class FactNormalizer:
    """
    パース済みXBRLとcontext_mapから、投資分析用の標準構造を生成する。
    """

    def __init__(self, parsed_data: dict[str, Any], context_map: dict[str, dict[str, Any]]) -> None:
        """
        Args:
            parsed_data: XBRLParser.parse() の戻り値（doc_id, taxonomy_version, facts）
            context_map: ContextResolver.build_context_map() の戻り値
        """
        self._parsed = parsed_data
        self._context_map = context_map
        self._current_year_end: str | None = None
        self._prior_year_end: str | None = None
        self._compute_year_ends()

    def _compute_year_ends(self) -> None:
        """context_mapから当期・前期の基準日を算出。"""
        self._current_year_end, self._prior_year_end = _current_and_prior_year_ends(self._context_map)
        if self._current_year_end:
            logger.debug("current_year_end: %s", self._current_year_end)
        if self._prior_year_end:
            logger.debug("prior_year_end: %s", self._prior_year_end)

    def _fact_context_info(self, context_ref: str) -> dict[str, Any]:
        """contextRefから type / is_current_year / is_prior_year を返す。"""
        ctx = self._context_map.get(context_ref, {})
        t = ctx.get("type", "")
        is_current = False
        is_prior = False
        if t == "duration":
            end = ctx.get("end_date", "")
            is_current = end == self._current_year_end if self._current_year_end else False
            is_prior = end == self._prior_year_end if self._prior_year_end else False
        elif t == "instant":
            date = ctx.get("date", "")
            is_current = date == self._current_year_end if self._current_year_end else False
            is_prior = date == self._prior_year_end if self._prior_year_end else False
        return {"type": t, "is_current_year": is_current, "is_prior_year": is_prior}

    def _pick_duration_facts(
        self,
        facts: list[dict[str, str]],
        tag_keywords: list[tuple[str, str]],
        is_current: bool,
    ) -> dict[str, int | None]:
        """
        duration系のfactから、連結優先・同一キーは先頭マッチ優先でPL/CF用辞書を構築。
        同一output keyに対して複数のkeywordが定義されている場合、先にマッチしたものを採用する。
        """
        out: dict[str, int | None] = {}
        for keyword, key in tag_keywords:
            if key in out and out[key] is not None:
                continue
            consolidated_candidates: list[dict[str, str]] = []
            non_consolidated_candidates: list[dict[str, str]] = []
            for f in facts:
                if not _tag_matches(f.get("tag", ""), keyword):
                    continue
                ctx_ref = f.get("contextRef", "")
                if _has_member_dimension(ctx_ref):
                    continue
                info = self._fact_context_info(ctx_ref)
                if info["type"] != "duration":
                    continue
                if is_current and not info["is_current_year"]:
                    continue
                if not is_current and not info["is_prior_year"]:
                    continue
                if _is_consolidated_context(ctx_ref):
                    consolidated_candidates.append(f)
                else:
                    non_consolidated_candidates.append(f)
            chosen = consolidated_candidates[0] if consolidated_candidates else (non_consolidated_candidates[0] if non_consolidated_candidates else None)
            if chosen is not None:
                out[key] = _parse_numeric_value(chosen.get("value"))
            elif key not in out:
                out[key] = None
        return out

    def _extract_pl(
        self,
        facts: list[dict[str, str]],
        is_current: bool,
    ) -> dict[str, int | None]:
        """PL抽出。EPSは再計算可能なため抽出しない（valuation-engineで算出）。"""
        return self._pick_duration_facts(facts, PL_TAGS, is_current=is_current)

    def _pick_duration_facts_allow_non_consolidated(
        self,
        facts: list[dict[str, str]],
        tag_keywords: list[tuple[str, str]],
        is_current: bool,
    ) -> dict[str, float | None]:
        """配当等の個別ベース項目用。連結で見つからなければ個別からも取得する。値はfloat。"""
        out: dict[str, float | None] = {}
        for keyword, key in tag_keywords:
            if key in out and out[key] is not None:
                continue
            consolidated_candidates: list[dict[str, str]] = []
            non_consolidated_candidates: list[dict[str, str]] = []
            for f in facts:
                if not _tag_matches(f.get("tag", ""), keyword):
                    continue
                ctx_ref = f.get("contextRef", "")
                if _has_member_dimension(ctx_ref):
                    continue
                info = self._fact_context_info(ctx_ref)
                if info["type"] != "duration":
                    continue
                if is_current and not info["is_current_year"]:
                    continue
                if not is_current and not info["is_prior_year"]:
                    continue
                if _is_consolidated_context(ctx_ref):
                    consolidated_candidates.append(f)
                else:
                    non_consolidated_candidates.append(f)
            chosen = consolidated_candidates[0] if consolidated_candidates else (
                non_consolidated_candidates[0] if non_consolidated_candidates else None
            )
            if chosen is not None:
                out[key] = _parse_float_value(chosen.get("value"))
            elif key not in out:
                out[key] = None
        return out

    def _extract_bs(
        self,
        facts: list[dict[str, str]],
        is_current: bool,
    ) -> dict[str, int | None]:
        """BS抽出。タグから取得した値をそのまま格納。補完・再構成は行わない。"""
        return self._pick_instant_facts(facts, BS_TAGS, is_current=is_current)

    def _pick_instant_facts(
        self,
        facts: list[dict[str, str]],
        tag_keywords: list[tuple[str, str]],
        is_current: bool,
    ) -> dict[str, int | None]:
        """
        instant系のfactから、BS用辞書を構築。
        同一output keyは先頭マッチ優先。セグメント・メンバーdimensionは除外。
        """
        out: dict[str, int | None] = {}
        target_date = self._current_year_end if is_current else self._prior_year_end
        if not target_date:
            for _, key in tag_keywords:
                if key not in out:
                    out[key] = None
            return out
        for keyword, key in tag_keywords:
            if key in out and out[key] is not None:
                continue
            consolidated_candidates: list[dict[str, str]] = []
            non_consolidated_candidates: list[dict[str, str]] = []
            for f in facts:
                if not _tag_matches(f.get("tag", ""), keyword):
                    continue
                ctx_ref = f.get("contextRef", "")
                if _has_member_dimension(ctx_ref):
                    continue
                ctx = self._context_map.get(ctx_ref, {})
                if ctx.get("type") != "instant":
                    continue
                if ctx.get("date") != target_date:
                    continue
                if _is_consolidated_context(ctx_ref):
                    consolidated_candidates.append(f)
                else:
                    non_consolidated_candidates.append(f)
            chosen = consolidated_candidates[0] if consolidated_candidates else (non_consolidated_candidates[0] if non_consolidated_candidates else None)
            if chosen is not None:
                out[key] = _parse_numeric_value(chosen.get("value"))
            elif key not in out:
                out[key] = None
        return out

    def _pick_dei(self, facts: list[dict[str, str]]) -> dict[str, Any]:
        """DEIタグから security_code, company_name, accounting_standard, is_consolidated, fiscal_year_end を取得。連結優先。"""
        result: dict[str, Any] = {
            "security_code": None,
            "company_name": None,
            "accounting_standard": None,
            "is_consolidated": True,
            "fiscal_year_end": None,
        }
        for keyword, key in DEI_TAGS:
            consolidated_f: dict[str, str] | None = None
            non_consolidated_f: dict[str, str] | None = None
            for f in facts:
                if not _tag_matches(f.get("tag", ""), keyword):
                    continue
                if _is_consolidated_context(f.get("contextRef", "")):
                    consolidated_f = f
                    break
                else:
                    if non_consolidated_f is None:
                        non_consolidated_f = f
            chosen = consolidated_f or non_consolidated_f
            if chosen is None:
                # デバッグログ: タグが見つからない場合
                if key == "security_code":
                    logger.warning(
                        "SecurityCodeDEI タグが見つかりませんでした。"
                        "doc_id=%s, 検索キーワード=%s",
                        self._parsed.get("doc_id", "unknown"),
                        keyword
                    )
                continue
            if key == "is_consolidated_dei":
                result["is_consolidated"] = _parse_consolidated_dei(chosen.get("value", ""))
            elif key == "security_code":
                result["security_code"] = (chosen.get("value") or "").strip() or None
                if result["security_code"]:
                    logger.info(
                        "security_code を抽出しました: %s (doc_id=%s)",
                        result["security_code"],
                        self._parsed.get("doc_id", "unknown")
                    )
            elif key == "company_name":
                result["company_name"] = (chosen.get("value") or "").strip() or None
            elif key == "accounting_standard":
                result["accounting_standard"] = (chosen.get("value") or "").strip() or None
            elif key in ("current_period_end_date", "current_fiscal_year_end_date"):
                # fiscal_year_end を優先順位で取得（CurrentFiscalYearEndDateDEI > CurrentPeriodEndDateDEI）
                value = (chosen.get("value") or "").strip()
                if value and result["fiscal_year_end"] is None:
                    result["fiscal_year_end"] = value
                elif key == "current_fiscal_year_end_date" and value:
                    # CurrentFiscalYearEndDateDEI の方が優先
                    result["fiscal_year_end"] = value
        
        # security_code が None の場合、警告を出力
        if result["security_code"] is None:
            logger.warning(
                "security_code が抽出できませんでした。doc_id=%s",
                self._parsed.get("doc_id", "unknown")
            )
        return result

    def _detect_report_type(self) -> str:
        """
        書類種別を判定。
        有価証券報告書 → "annual"
        四半期報告書 → "quarterly"
        判定不能 → "unknown"
        """
        # 暫定的に "annual" を返す（有価証券報告書が最も一般的）
        # 将来的には、XBRLParser からファイル名を取得して判定する
        return "annual"

    def _build_period(self, is_current: bool) -> dict[str, str] | None:
        """duration contextからperiod(start/end)を構築する。"""
        target_end = self._current_year_end if is_current else self._prior_year_end
        if not target_end:
            return None
        for ctx in self._context_map.values():
            if ctx.get("type") == "duration" and ctx.get("end_date") == target_end:
                start = ctx.get("start_date")
                if start:
                    return {"start": start, "end": target_end}
        return None

    def normalize(self) -> dict[str, Any]:
        """
        正規化結果を返す。
        current_year / prior_year それぞれに pl, bs, cf, dividend, period を持つ構造。
        """
        facts = self._parsed.get("facts") or []
        dei = self._pick_dei(facts)

        current_pl = self._extract_pl(facts, is_current=True)
        prior_pl = self._extract_pl(facts, is_current=False)
        current_bs = self._extract_bs(facts, is_current=True)
        prior_bs = self._extract_bs(facts, is_current=False)
        current_cf = self._pick_duration_facts(facts, CF_TAGS, is_current=True)
        prior_cf = self._pick_duration_facts(facts, CF_TAGS, is_current=False)
        current_dividend = self._pick_duration_facts_allow_non_consolidated(
            facts, DIVIDEND_TAGS, is_current=True,
        )
        prior_dividend = self._pick_duration_facts_allow_non_consolidated(
            facts, DIVIDEND_TAGS, is_current=False,
        )
        current_period = self._build_period(is_current=True)
        prior_period = self._build_period(is_current=False)

        report_type = self._detect_report_type()

        consolidation_type = "consolidated" if dei["is_consolidated"] else "non_consolidated"

        result: dict[str, Any] = {
            "doc_id": self._parsed.get("doc_id", ""),
            "security_code": dei["security_code"],
            "company_name": dei["company_name"],
            "accounting_standard": dei["accounting_standard"],
            "is_consolidated": dei["is_consolidated"],
            "consolidation_type": consolidation_type,
            "fiscal_year_end": dei["fiscal_year_end"],
            "report_type": report_type,
            "current_year": {
                "pl": current_pl,
                "bs": current_bs,
                "cf": current_cf,
                "dividend": current_dividend,
            },
            "prior_year": {
                "pl": prior_pl,
                "bs": prior_bs,
                "cf": prior_cf,
                "dividend": prior_dividend,
            },
        }

        if current_period:
            result["current_year"]["period"] = current_period
        if prior_period:
            result["prior_year"]["period"] = prior_period

        return result
