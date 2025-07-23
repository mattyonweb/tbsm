from decimal import Decimal

from django.db import models
from django.db.transaction import atomic
from django.utils import timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from contracts.models import Thing, Ownership


# Create your models here.
class Corporation(models.Model):
    full_name = models.CharField(max_length=96, blank=False, null=False, verbose_name="Full name")
    ticker    = models.CharField(max_length=8, blank=False, null=False, verbose_name="Ticker")
    bankrupt  = models.DateTimeField(null=True, blank=True)

    @property
    def cash(self) -> Decimal:
        if own_money := Ownership.objects.filter(corporation=self, thing__currency__ticker="€").first():
            return own_money.amount
        return Decimal(0)

    def has(self, thing: "Thing") -> Optional["Ownership"] :
        return Ownership.objects.filter(corporation=self, thing=thing).first()

    def pay(self, amount: Decimal, to: "Corporation") -> tuple[Decimal, bool]:
        # TODO: diventa un special case di transfer ownership
        with atomic():
            payable_amount = min(amount, self.balance)
            bankrupt       = payable_amount < amount
            if bankrupt:
                self.bankrupt = timezone.now()
            to.balance += payable_amount
            to.save()
            self.save()

        return payable_amount, bankrupt

    def transfer_ownership(self, obj, amount: Decimal, to: "Corporation"):
        with atomic():
            payable_amount = min(amount, self.balance)
            bankrupt       = payable_amount < amount
            if bankrupt:
                self.bankrupt = timezone.now()
            to.balance += payable_amount
            to.save()
            self.save()