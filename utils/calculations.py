from decimal import Decimal


def percent(full_amount: Decimal, percent: Decimal, decimal_figures=2) -> Decimal:
    return (full_amount * percent / Decimal("100.00")).quantize(Decimal("1.00"))