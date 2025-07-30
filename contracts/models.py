import datetime
from decimal import Decimal

from django.db import models
from django.db.models import CheckConstraint, Q
from django.db.transaction import atomic
from django.utils import timezone

from accounts.models import CustomUser
from corporations.models import Corporation

# ====================================================================================================================
# ====================================================================================================================
# Contracts

class TimelyAction(models.Model):
    class Regularity(models.IntegerChoices):
        EVERY   = 1, "Every"
        EXACTLY_IN = 2, "Exactly in"
        EXACTLY_AT = 3, "Exactly at"
        WHEN    = 4, "When"

    regularity = models.SmallIntegerField(
        choices=Regularity.choices,
        default=Regularity.EVERY,
        null=False, blank=False,
        verbose_name="Regularity"
    )

    starting_after = models.DurationField(
        null=True, blank=True,
        default=datetime.timedelta(0),
        verbose_name="After date"
    )

    every = models.DurationField(
        null=True, blank=True,
        verbose_name="Every"
    )

    repeat_times = models.IntegerField(
        null=True, blank=True,
        verbose_name="Repeat times"
    )

    exactly_in = models.DurationField(
        null=True, blank=True,
        verbose_name="Exactly in"
    )

    exactly_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Exactly at"
    )

    when_condition = models.JSONField(
        null=True, blank=True,
        verbose_name="When the following condition is true"
    )

    def __str__(self):
        match self.regularity:
            case TimelyAction.Regularity.EVERY:
                return f"Every {self.every} for {self.repeat_times} time(s)" + (f" starting in {self.starting_after}" if self.starting_after else "")
            case TimelyAction.Regularity.EXACTLY_IN:
                return f"Once in {self.exactly_in}"
            case _:
                raise Exception("Not yet implemented")

    def absolutize(self, start_date: datetime.datetime) -> list[datetime.datetime]:
        match self.regularity:
            case TimelyAction.Regularity.EVERY:
                date = start_date
                if self.starting_after:
                    date += self.starting_after
                return [date + i * self.every for i in range(self.repeat_times)]
            case TimelyAction.Regularity.EXACTLY_IN:
                return [start_date + self.exactly_in]
            case TimelyAction.Regularity.EXACTLY_AT:
                return [self.exactly_at]
            case _:
                raise Exception("Not yet implemented")

# ta_bond_coupon_payment = TimelyAction(
#     regularity=TimelyAction.Regularity.EVERY,
#     every=datetime.timedelta(days=30),
#     repeat_times=4
# )
# ta_bond_final_payment = TimelyAction(
#     regularity=TimelyAction.Regularity.EXACTLY_IN,
#     exactly_in=datetime.timedelta(days=120)
# )

# ===============================================================================================================

class RepaymentTemplate(models.Model):
    class Variability(models.IntegerChoices):
        FIXED = 1, "Fixed"
        VARIABLE = 2, "Variable"

    timely_action = models.ForeignKey(TimelyAction, on_delete=models.CASCADE, verbose_name="Timely action")

    variability = models.SmallIntegerField(
        choices=Variability.choices,
        default=Variability.FIXED,
        null=False, blank=False,
        verbose_name="Variability"
    )

    fixed_amount = models.DecimalField(
        null=True, blank=True,
        max_digits=15, decimal_places=2,
        verbose_name="Fixed amount"
    )

    variable_amount = models.JSONField(
        null=True, blank=True,
        verbose_name="Variable amount formula"
    )

    traded_thing = models.ForeignKey("things.Thing", on_delete=models.CASCADE, blank=False, null=False)

    def __str__(self):
        match self.variability:
            case RepaymentTemplate.Variability.FIXED:
                return f"{self.fixed_amount}€ {self.timely_action}"
            case RepaymentTemplate.Variability.VARIABLE:
                return f"{self.variable_amount}€ {self.timely_action}"
        raise Exception("unreachable")

    def absolutize_amount(self) -> Decimal | dict:
        match self.variability:
            case RepaymentTemplate.Variability.FIXED:
                return self.fixed_amount
            case RepaymentTemplate.Variability.VARIABLE:
                return self.variable_amount
        raise Exception("unreachable")



# rp_bond_coupon = RepaymentTemplate(
#     timely_action=ta_bond_coupon_payment,
#     variability=RepaymentTemplate.Variability.FIXED,
#     fixed_amount=Decimal("3.5")
# )
# rp_bond_final_payment = RepaymentTemplate(
#     timely_action=ta_bond_final_payment,
#     variability=RepaymentTemplate.Variability.FIXED,
#     fixed_amount=Decimal("100")
# )

# =============================================================================================

class Contract(models.Model):
    nominal_price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Nominal price")
    repayments = models.ManyToManyField(RepaymentTemplate, verbose_name="Repayments")

    activated = models.DateTimeField(null=True, blank=True, verbose_name="Activation date")
    emitter   = models.ForeignKey(
        Corporation, on_delete=models.CASCADE, null=False, blank=False,
        related_name="emitter", verbose_name="Emitter user"
    )
    receiver  = models.ForeignKey(
        Corporation, on_delete=models.CASCADE, null=True, blank=True,
        related_name="receiver", verbose_name="Receiver user"
    )

    def activate(self, receiver: Corporation):
        self.receiver  = receiver
        self.activated = timezone.now()

        for repay in self.repayments.all():
            dates: list = repay.timely_action.absolutize(self.activated)
            for date in dates:
                PaymentScheduler.objects.get_or_create(contract=self, repayment=repay, ts=date)

        self.save()




def create_bond_fixed(nominal_price: Decimal, coupon_percentage:Decimal=None, coupon_money:Decimal=None):
    assert not (coupon_percentage is None and coupon_money is None)

    coupon_val = 0
    if coupon_percentage is not None:
        coupon_val = nominal_price * coupon_percentage
    if coupon_money is not None:
        coupon_val += coupon_money

    ta_bond_coupon_payment, _ = TimelyAction.objects.get_or_create(
        regularity=TimelyAction.Regularity.EVERY,
        every=datetime.timedelta(days=30),
        repeat_times=4
    )
    ta_bond_final_payment, _ = TimelyAction.objects.get_or_create(
        regularity=TimelyAction.Regularity.EXACTLY_IN,
        exactly_in=datetime.timedelta(days=120)
    )
    rp_bond_coupon, _ = RepaymentTemplate.objects.get_or_create(
        timely_action=ta_bond_coupon_payment,
        variability=RepaymentTemplate.Variability.FIXED,
        fixed_amount=coupon_val
    )
    rp_bond_final_payment, _ = RepaymentTemplate.objects.get_or_create(
        timely_action=ta_bond_final_payment,
        variability=RepaymentTemplate.Variability.FIXED,
        fixed_amount=nominal_price
    )

    ct = Contract()
    ct.nominal_price = nominal_price
    ct.save()
    ct.repayments.set([rp_bond_coupon, rp_bond_final_payment])
    ct.save()


# ==============================================================================


class PaymentScheduler(models.Model):
    contract  = models.ForeignKey(Contract, on_delete=models.CASCADE, null=False, blank=False, verbose_name="Contract")
    repayment = models.ForeignKey(RepaymentTemplate, on_delete=models.CASCADE, null=False, blank=False, verbose_name="Repayment")
    ts        = models.DateTimeField(null=False, blank=False, verbose_name="Repayment date")
    was_processed = models.BooleanField(default=False, verbose_name="Payment was checked at or nearly after the due date")
    paid      = models.BooleanField(default=False, verbose_name="Paid")
    missed_payment = models.BooleanField(default=False, verbose_name="Missed payment")

    def perform_payment(self):
        with atomic():
            if self.was_processed:
                # TODO: log an error
                return

            # Mark as checked first to prevent double processing
            self.was_processed = True
            self.save(update_fields=["was_processed"]) # TODO: unneded in atomic?

            emitter: Corporation  = self.contract.emitter
            receiver: Corporation = self.contract.receiver

            # There should always be a receiver!
            if not receiver:
                raise Exception("Contract was not activated, but was scheduled?")

            # Get the amount to transfer from the repayment template
            repayment_amount = self.repayment.absolutize_amount()

            # Handle variable amount (should be a formula, but for now treat as decimal)
            if isinstance(repayment_amount, dict):
                print(f"WARNING: Variable payment formulas not yet implemented for payment {self.id}")
                raise Exception("Not yet implemented")

            # Get the thing being transferred from the repayment template
            thing_to_transfer = self.repayment.traded_thing

            # Execute the transfer
            transferred_amount, has_bankrupted = emitter.transfer_ownership(
                thing_to_transfer, repayment_amount, receiver
            )

            # Update payment status
            if transferred_amount == repayment_amount:
                self.paid = True
                print(f"Payment {self.id} completed: {transferred_amount} of {thing_to_transfer}")
            else:
                self.missed_payment = True
                print(
                    f"Payment {self.id} partially completed: {transferred_amount}/{repayment_amount} of {thing_to_transfer}")

            if has_bankrupted:
                print(f"Corporation {emitter.ticker} declared bankrupt during payment {self.id}")

            self.save()



# Create your models here.
# Contract(
#     initial_conditions={
#         "nominal_price": 100,
#         "conditions_on_buyer": [],
#         "conditions_on_seller": [],
#         "custom_attributes":{}
#     },
#     repayments=[
#         ("every", datetime.timedelta(days=7), "times", 4, lambda cnt: cnt.initial_conditions["nominal_price"] * Decimal("3.15")),
#         ("finally", )
#     }
#
# )

