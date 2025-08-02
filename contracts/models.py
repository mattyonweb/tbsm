import datetime
import logging
from decimal import Decimal

from django.db import models
from django.db.transaction import atomic
from django.utils import timezone

from accounts.models import CustomUser
from contracts import slfps
from contracts.slfps import formula_human_readable
from corporations.models import Corporation, TransactionLog
from utils.calculations import clip
from utils.models import BaseLogModel

logger = logging.getLogger("contracts_models")

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
                return f"{formula_human_readable(self.variable_amount['formula'])} {self.timely_action}"
        raise Exception("unreachable")



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
            for i, date in enumerate(dates):
                ScheduledPayment.objects.get_or_create(
                    contract=self, repayment=repay, ts=date, execution_order=i
                )

        self.save()


# ==============================================================================


class ScheduledPayment(models.Model):
    contract  = models.ForeignKey(Contract, on_delete=models.CASCADE, null=False, blank=False, verbose_name="Contract")
    repayment = models.ForeignKey(RepaymentTemplate, on_delete=models.CASCADE, null=False, blank=False, verbose_name="Repayment")
    execution_order = models.SmallIntegerField(verbose_name="Execution order", null=False, blank=False, default=0)
    ts        = models.DateTimeField(null=False, blank=False, verbose_name="Repayment date")
    was_processed = models.BooleanField(default=False, verbose_name="Payment was checked at or nearly after the due date")
    paid      = models.BooleanField(default=False, verbose_name="Paid")
    missed_payment = models.BooleanField(default=False, verbose_name="Missed payment")

    def absolutize_amount(self) -> Decimal:
        """
        Calculate the actual payment amount for this scheduled payment.
        
        Returns the fixed amount if the repayment is fixed, or evaluates
        the variable formula using the SLFPS interpreter if variable.
        
        Returns:
            Decimal: The calculated payment amount
        """
        # When the payment is simple:
        if self.repayment.variability == RepaymentTemplate.Variability.FIXED:
            return self.repayment.fixed_amount

        # When the payment has to be calculated in real time
        complex_payment = self.repayment.variable_amount
        formula = complex_payment["formula"]
        return slfps.calculate(formula, self)


    def perform_payment(self):
        with atomic():
            if self.was_processed:
                logger.error("Attempted to perform a payment already paid", extra={"scheduled_payment": self})
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
            repayment_amount = self.absolutize_amount()

            # Get the thing being transferred from the repayment template
            thing_to_transfer = self.repayment.traded_thing

            # Execute the transfer
            transferred_amount, has_bankrupted = emitter.transfer_ownership(
                thing_to_transfer, repayment_amount, receiver
            )

            # Update payment status
            if transferred_amount == repayment_amount:
                self.paid = True
                logger.info(f"Payment {self.id} completed: {transferred_amount} of {thing_to_transfer}")
            else:
                self.missed_payment = True
                logger.warning(
                    f"Payment {self.id} partially completed: {transferred_amount}/{repayment_amount} of {thing_to_transfer}")

            if has_bankrupted:
                logger.error(f"Corporation {emitter.ticker} declared bankrupt during payment {self.id}")

            self.save()

            log = TransactionLog()
            log.giver = emitter
            log.taker = receiver
            log.thing = thing_to_transfer
            log.amount_scheduled = repayment_amount
            log.amount_actually_given = transferred_amount
            log.causal = "Contract scheduled payment"
            log.payment_schedule = self
            log.save()



class Rating(models.Model):
    corporation = models.ForeignKey(Corporation, on_delete=models.CASCADE, null=False, blank=False)
    rating      = models.DecimalField(max_digits=8, decimal_places=5, null=False, blank=False)
    is_newbie   = models.BooleanField(default=False) # TODO: messo in creazione utente e tolto dopo 7gg.

    @staticmethod
    def payment_was_ok(self, sp: ScheduledPayment, amount: Decimal):
        corp: Corporation = sp.contract.emitter
        current_amount = corp.has_how_many(sp.repayment.traded_thing)

        if current_amount == 0:
            increase = 2
        else:
            increase = clip(2 * (amount / current_amount).quantize(Decimal("1.0000")), 0, 2)

        rating = Rating.objects.get(corporation=corp)
        rating.rating = clip(rating.rating + increase, 0, 100)
        rating.save()

        RatingLog.objects.create(
            rating=rating, delta=increase, scheduled_payment=sp
        )

    @staticmethod
    def payment_was_not_ok(self, sp: ScheduledPayment, amount_expected: Decimal, amount_paid: Decimal):
        corp: Corporation = sp.contract.emitter

        decrease = -40

        rating = Rating.objects.get(corporation=corp)
        rating.rating = clip(rating.rating + decrease, 0, 100)
        rating.save()

        RatingLog.objects.create(
            rating=rating, delta=decrease, scheduled_payment=sp
        )


class RatingLog(BaseLogModel):
    rating = models.ForeignKey(Rating, on_delete=models.CASCADE)
    # theoretical_delta = models.DecimalField(max_digits=8, decimal_places=4)
    delta      = models.DecimalField(max_digits=8, decimal_places=4)
    scheduled_payment = models.ForeignKey(ScheduledPayment, on_delete=models.CASCADE)
