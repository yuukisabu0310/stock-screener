"""
FinancialMaster（Phase3）
Normalizer出力から投資分析用財務指標を計算する。再構成・欠損補完・指標計算を担当。
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_equity(bs: dict[str, Any]) -> int | None:
    """Equity統合。優先順位: shareholders_equity > equity > net_assets。"""
    v = bs.get("shareholders_equity")
    if v is not None:
        return int(v) if isinstance(v, (int, float)) else None
    v = bs.get("equity")
    if v is not None:
        return int(v) if isinstance(v, (int, float)) else None
    v = bs.get("net_assets")
    if v is not None:
        return int(v) if isinstance(v, (int, float)) else None
    return None


def _resolve_interest_bearing_debt(bs: dict[str, Any]) -> int | None:
    """InterestBearingDebt。タグ値があればそれ、なければ内訳合算。全部NoneならNone。"""
    v = bs.get("interest_bearing_debt")
    if v is not None:
        return int(v) if isinstance(v, (int, float)) else None
    keys = [
        "short_term_borrowings",
        "long_term_borrowings",
        "bonds_payable",
        "current_portion_of_long_term_borrowings",
    ]
    parts = [bs.get(k) for k in keys]
    if all(p is None for p in parts):
        return None
    total = 0
    for p in parts:
        if p is not None and isinstance(p, (int, float)):
            total += int(p)
    return total


def _safe_div(num: int | float | None, denom: int | float | None) -> float | None:
    """0除算回避。分母がNoneまたは0ならNone。"""
    if num is None or denom is None:
        return None
    try:
        d = float(denom)
    except (TypeError, ValueError):
        return None
    if d == 0:
        return None
    try:
        return float(num) / d
    except (TypeError, ValueError):
        return None


def _growth(current: int | float | None, prior: int | float | None) -> float | None:
    """成長率 (current - prior) / prior。priorがNone/0ならNone。"""
    if current is None or prior is None:
        return None
    try:
        p = float(prior)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    try:
        return (float(current) - p) / p
    except (TypeError, ValueError):
        return None


def _compute_metrics(
    pl: dict[str, Any],
    bs: dict[str, Any],
    cf: dict[str, Any],
) -> dict[str, float | None]:
    """単年分のPL/BS/CFから指標を計算。"""
    equity = _resolve_equity(bs)
    interest_bearing_debt = _resolve_interest_bearing_debt(bs)
    total_assets = bs.get("total_assets")
    if total_assets is not None and not isinstance(total_assets, (int, float)):
        total_assets = None

    net_sales = pl.get("net_sales")
    operating_income = pl.get("operating_income")
    profit_loss = pl.get("profit_loss")
    operating_cf = cf.get("net_cash_provided_by_operating_activities")
    investing_cf = cf.get("net_cash_used_in_investing_activities")

    # FCF = operating_cf + investing_cf（投資CFは通常マイナス値なので加算で正しい）
    fcf: int | float | None = None
    if operating_cf is not None and investing_cf is not None:
        try:
            fcf = float(operating_cf) + float(investing_cf)
        except (TypeError, ValueError):
            pass
    elif operating_cf is not None:
        try:
            fcf = float(operating_cf)
        except (TypeError, ValueError):
            pass

    return {
        "equity": float(equity) if equity is not None else None,
        "interest_bearing_debt": float(interest_bearing_debt) if interest_bearing_debt is not None else None,
        "total_assets": float(total_assets) if total_assets is not None else None,
        "net_sales": float(net_sales) if net_sales is not None else None,
        "operating_income": float(operating_income) if operating_income is not None else None,
        "profit_loss": float(profit_loss) if profit_loss is not None else None,
        "free_cash_flow": float(fcf) if fcf is not None else None,
        "roe": _safe_div(profit_loss, equity),
        "roa": _safe_div(profit_loss, total_assets),
        "operating_margin": _safe_div(operating_income, net_sales),
        "net_margin": _safe_div(profit_loss, net_sales),
        "equity_ratio": _safe_div(equity, total_assets),
        "de_ratio": _safe_div(interest_bearing_debt, equity),
    }


class FinancialMaster:
    """
    Normalizer出力を受け取り、投資分析用指標を計算する。
    再構成・欠損補完・財務指標計算を担当。Normalizerには影響しない。
    """

    def __init__(self, normalized_data: dict[str, Any]) -> None:
        """
        Args:
            normalized_data: FactNormalizer.normalize() の戻り値。
        """
        self._data = normalized_data

    def compute(self) -> dict[str, Any]:
        """
        current_year / prior_year それぞれの metrics を計算し、
        成長率（sales_growth, profit_growth, eps_growth）を付与して返す。
        """
        current = self._data.get("current_year") or {}
        prior = self._data.get("prior_year") or {}

        current_pl = current.get("pl") or {}
        current_bs = current.get("bs") or {}
        current_cf = current.get("cf") or {}
        prior_pl = prior.get("pl") or {}
        prior_bs = prior.get("bs") or {}
        prior_cf = prior.get("cf") or {}

        current_metrics = _compute_metrics(current_pl, current_bs, current_cf)
        prior_metrics = _compute_metrics(prior_pl, prior_bs, prior_cf)

        # 成長率（当期 vs 前期）を current_year.metrics に追加
        sales_growth = _growth(
            current_metrics.get("net_sales") or current_pl.get("net_sales"),
            prior_metrics.get("net_sales") or prior_pl.get("net_sales"),
        )
        profit_growth = _growth(
            current_metrics.get("profit_loss") or current_pl.get("profit_loss"),
            prior_metrics.get("profit_loss") or prior_pl.get("profit_loss"),
        )
        current_eps = current_pl.get("earnings_per_share")
        prior_eps = prior_pl.get("earnings_per_share")
        eps_growth = _growth(
            float(current_eps) if current_eps is not None else None,
            float(prior_eps) if prior_eps is not None else None,
        )
        current_metrics["sales_growth"] = sales_growth
        current_metrics["profit_growth"] = profit_growth
        current_metrics["eps_growth"] = eps_growth

        result = {
            "doc_id": self._data.get("doc_id", ""),
            "current_year": {"metrics": current_metrics},
            "prior_year": {"metrics": prior_metrics},
        }
        logger.info("FinancialMaster compute: doc_id=%s", result["doc_id"])
        return result
