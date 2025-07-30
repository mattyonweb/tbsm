import datetime
from decimal import Decimal

from contracts.models import Contract, logger, TimelyAction, RepaymentTemplate
from corporations.models import Corporation


def create_bond(
        emitter: Corporation,
        nominal_price: Decimal,
        maturity_days: int,
        currency_thing,
        coupon_amount: Decimal = None,
        coupon_frequency_days: int = None,
        num_coupons: int = None
) -> Contract:
    """
    Create a bond contract with configurable coupons and maturity.

    Args:
        emitter: Corporation issuing the bond
        nominal_price: Final payout amount at maturity
        maturity_days: Days until bond matures
        currency_thing: Thing object representing the currency for payments
        coupon_amount: Fixed amount per coupon payment (optional)
        coupon_frequency_days: Days between coupon payments (optional)
        num_coupons: Total number of coupon payments (optional)

    Returns:
        Contract: The created bond contract
    """
    logger.info(f"Creating bond for {emitter.ticker}: nominal={nominal_price}, maturity={maturity_days} days")

    repayment_templates = []

    # Create coupon payments if specified
    if coupon_amount and coupon_frequency_days and num_coupons:
        ta_coupon = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EVERY,
            every=datetime.timedelta(days=coupon_frequency_days),
            repeat_times=num_coupons
        )

        rp_coupon = RepaymentTemplate.objects.create(
            timely_action=ta_coupon,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=coupon_amount,
            traded_thing=currency_thing
        )
        repayment_templates.append(rp_coupon)
        logger.debug(f"Created {num_coupons} coupons of {coupon_amount} every {coupon_frequency_days} days")

    # Create final payment at maturity
    ta_final = TimelyAction.objects.create(
        regularity=TimelyAction.Regularity.EXACTLY_IN,
        exactly_in=datetime.timedelta(days=maturity_days)
    )

    rp_final = RepaymentTemplate.objects.create(
        timely_action=ta_final,
        variability=RepaymentTemplate.Variability.FIXED,
        fixed_amount=nominal_price,
        traded_thing=currency_thing
    )
    repayment_templates.append(rp_final)

    # Create the contract
    contract = Contract.objects.create(
        nominal_price=nominal_price,
        emitter=emitter
    )
    contract.repayments.set(repayment_templates)

    logger.info(f"Bond created with ID {contract.id}")
    return contract


def create_simple_bond(
    emitter: Corporation,
    nominal_price: Decimal,
    maturity_days: int,
    currency_thing
) -> Contract:
    """
    Create a simple zero-coupon bond (no intermediate payments).

    Args:
        emitter: Corporation issuing the bond
        nominal_price: Amount paid at maturity
        maturity_days: Days until maturity
        currency_thing: Thing object representing the currency

    Returns:
        Contract: The created bond contract
    """
    return create_bond(
        emitter=emitter,
        nominal_price=nominal_price,
        maturity_days=maturity_days,
        currency_thing=currency_thing
    )


def create_coupon_bond(
    emitter: Corporation,
    nominal_price: Decimal,
    maturity_days: int,
    currency_thing,
    coupon_rate: Decimal,
    coupon_frequency_days: int = 30
) -> Contract:
    """
    Create a coupon bond with regular interest payments.

    Args:
        emitter: Corporation issuing the bond
        nominal_price: Principal amount paid at maturity
        maturity_days: Days until maturity
        currency_thing: Thing object representing the currency
        coupon_rate: Annual interest rate as decimal (e.g., 0.05 for 5%)
        coupon_frequency_days: Days between coupon payments (default 30)

    Returns:
        Contract: The created bond contract
    """
    # Calculate number of coupons based on frequency
    num_coupons = maturity_days // coupon_frequency_days

    # Calculate coupon amount (proportional to frequency)
    annual_coupon = nominal_price * coupon_rate
    coupon_amount = annual_coupon * (Decimal(coupon_frequency_days) / Decimal(365))

    return create_bond(
        emitter=emitter,
        nominal_price=nominal_price,
        maturity_days=maturity_days,
        currency_thing=currency_thing,
        coupon_amount=coupon_amount,
        coupon_frequency_days=coupon_frequency_days,
        num_coupons=num_coupons
    )
