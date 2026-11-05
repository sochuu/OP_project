"""Налоговые режимы РФ: НПД (самозанятость), УСН 6%, НДФЛ 13%."""

from dataclasses import dataclass

NPD_LIMIT = 2_400_000.0
NPD_BONUS_MAX = 10_000.0
# Полные ставки и ставки с бонусом (вычет уменьшает ставку: 4→3, 6→4)
NPD_FL_FULL, NPD_FL_BONUS = 0.04, 0.03
NPD_ORG_FULL, NPD_ORG_BONUS = 0.06, 0.04


@dataclass
class TaxBreakdown:
    regime: str
    year_income: float
    tax: float
    details: list
    warning: str = ""


def npd_tax(income_fl: float, income_org: float, bonus_left: float = NPD_BONUS_MAX) -> TaxBreakdown:
    """
    Вычет (бонус) 10 000 ₽ снижает ставку:
    с физлиц 4% → 3%, с ИП/юрлиц 6% → 4%, пока вычет не исчерпан.
    Расход вычета: 1% от дохода с ФЛ и 2% от дохода с организаций.
    """
    details = []
    tax = 0.0
    remaining_bonus = max(0.0, bonus_left)
    total = income_fl + income_org
    warning = ""
    if total > NPD_LIMIT:
        warning = f"Доход {total:.0f} ₽ превышает лимит НПД {NPD_LIMIT:.0f} ₽."

    def apply_chunk(amount: float, full: float, bonus_rate: float, bonus_spend_rate: float, label: str):
        nonlocal tax, remaining_bonus
        if amount <= 0:
            return
        if remaining_bonus <= 0:
            part = amount * full
            tax += part
            details.append({"part": label, "base": amount, "rate": full * 100, "tax": part})
            return
        # сколько дохода можно провести по сниженной ставке
        if bonus_spend_rate <= 0:
            reduced_base = amount
        else:
            reduced_base = min(amount, remaining_bonus / bonus_spend_rate)
        reduced_tax = reduced_base * bonus_rate
        spent = reduced_base * bonus_spend_rate
        remaining_bonus = max(0.0, remaining_bonus - spent)
        tax += reduced_tax
        details.append(
            {"part": f"{label} (бонус)", "base": reduced_base, "rate": bonus_rate * 100, "tax": reduced_tax}
        )
        rest = amount - reduced_base
        if rest > 1e-9:
            part = rest * full
            tax += part
            details.append({"part": f"{label} (полная ставка)", "base": rest, "rate": full * 100, "tax": part})

    apply_chunk(income_fl, NPD_FL_FULL, NPD_FL_BONUS, 0.01, "Доход от физлиц")
    apply_chunk(income_org, NPD_ORG_FULL, NPD_ORG_BONUS, 0.02, "Доход от ИП/юрлиц")
    details.append({"part": "Остаток бонуса, ₽", "base": remaining_bonus, "rate": 0, "tax": 0})
    return TaxBreakdown("npd", total, tax, details, warning)


def usn_tax(income: float, rate_percent: float = 6.0) -> TaxBreakdown:
    rate = rate_percent / 100.0
    tax = max(0.0, income) * rate
    return TaxBreakdown(
        "usn",
        income,
        tax,
        [{"part": "УСН «доходы»", "base": income, "rate": rate_percent, "tax": tax}],
    )


def ndfl_tax(income: float, rate_percent: float = 13.0) -> TaxBreakdown:
    rate = rate_percent / 100.0
    tax = max(0.0, income) * rate
    return TaxBreakdown(
        "ndfl",
        income,
        tax,
        [{"part": "НДФЛ", "base": income, "rate": rate_percent, "tax": tax}],
    )


def remaining_npd_bonus(start: float, earnings: list) -> float:
    """Остаток вычета после фактических доходов (1% ФЛ, 2% ЮЛ), по дате."""
    left = max(0.0, min(float(start), NPD_BONUS_MAX))
    ordered = sorted(earnings, key=lambda e: (e.earned_on, getattr(e, "id", 0) or 0))
    for e in ordered:
        rate = 0.01 if e.payer_type == "fl" else 0.02
        spent = min(left, max(0.0, float(e.amount)) * rate)
        left = max(0.0, left - spent)
    return round(left, 2)


def bonus_spent(start: float, earnings: list) -> float:
    return round(max(0.0, min(float(start), NPD_BONUS_MAX) - remaining_npd_bonus(start, earnings)), 2)


def calc_tax(regime: str, income_fl: float, income_org: float, settings) -> TaxBreakdown:
    total = income_fl + income_org
    if regime == "npd":
        return npd_tax(income_fl, income_org, settings.npd_bonus_left)
    if regime == "usn":
        return usn_tax(total, settings.usn_rate)
    return ndfl_tax(total, settings.ndfl_rate)
