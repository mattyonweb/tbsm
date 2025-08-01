from decimal import Decimal

from django.db import models
from django.db.models import DO_NOTHING, CASCADE
from django.db.transaction import atomic
from django.utils import timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from contracts.models import ScheduledPayment
    from things.models import Thing, Ownership, Currency


# Create your models here.
class Corporation(models.Model):
    full_name = models.CharField(max_length=96, blank=False, null=False, verbose_name="Full name")
    ticker    = models.CharField(max_length=8, blank=False, null=False, verbose_name="Ticker")
    bankrupt  = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.ticker

    @property
    def cash(self) -> Decimal:
        if own_money := Ownership.objects.filter(corporation=self, thing__currency__ticker="€").first():
            return own_money.amount
        return Decimal(0)

    def has(self, thing: "Thing") -> Optional["Ownership"] :
        return Ownership.objects.filter(corporation=self, thing=thing).first()

    def pay(self, amount: Decimal, to: "Corporation") -> tuple[Decimal, bool]:
        """
        A shortcut for an exchange of currency.
        :param amount:
        :param to:
        :return:
        """
        from things.models import Thing, Ownership, Currency
        
        euro_currency = Currency.objects.filter(ticker="€").first()
        euro_thing = Thing.objects.filter(currency=euro_currency).first()

        return self.transfer_ownership(euro_thing, amount, to)

    def transfer_ownership(self, thing: "Thing", amount: Decimal, to: "Corporation") -> tuple[Decimal, bool]:
        from things.models import Ownership
        
        with atomic():
            # Get or create ownership for the payer
            payer_ownership, _ = Ownership.objects.get_or_create(
                corporation=self, 
                thing=thing,
                defaults={'amount': Decimal(0)}
            )
            
            # Calculate how much can actually be transferred
            transferable_amount = min(amount, payer_ownership.amount)
            bankrupt = transferable_amount < amount
            
            if bankrupt:
                self.bankrupt = timezone.now()
                self.save()
            
            if transferable_amount > 0:
                # Reduce payer's ownership
                payer_ownership.amount -= transferable_amount
                payer_ownership.save()
                
                # Get or create ownership for the receiver
                receiver_ownership, _ = Ownership.objects.get_or_create(
                    corporation=to,
                    thing=thing,
                    defaults={'amount': Decimal(0)}
                )
                
                # Increase receiver's ownership
                receiver_ownership.amount += transferable_amount
                receiver_ownership.save()
                
                # Remove ownership record if amount becomes zero
                if payer_ownership.amount == 0:
                    payer_ownership.delete()

        return transferable_amount, bankrupt


class TransactionLog(models.Model):
    giver = models.ForeignKey(Corporation, on_delete=DO_NOTHING, related_name="giver", null=False)
    taker = models.ForeignKey(Corporation, on_delete=DO_NOTHING, related_name="taker", null=False)
    thing = models.ForeignKey("things.Thing", on_delete=DO_NOTHING, null=False)
    amount_scheduled = models.DecimalField(max_digits=15, decimal_places=2, null=False, blank=False)
    amount_actually_given = models.DecimalField(max_digits=15, decimal_places=2, null=False, blank=False)
    timestamp = models.DateTimeField(auto_now_add=True, null=False)
    causal = models.CharField(max_length=256, blank=False, null=True)
    payment_schedule = models.ForeignKey("contracts.ScheduledPayment", on_delete=CASCADE, null=False)

    @property
    def was_defaulted(self):
        return self.amount_actually_given < self.amount_scheduled

    def __str__(self):
        return f"{self.timestamp} - {self.causal}"
