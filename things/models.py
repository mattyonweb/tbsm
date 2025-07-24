from django.db import models
from django.db.models import CheckConstraint, Q

# ==========================================================================
# Tradable objects

class Material(models.Model):
    full_name = models.CharField(max_length=96, blank=False, null=False, verbose_name="Full name")
    ticker    = models.CharField(max_length=8, blank=False, null=False, verbose_name="Ticker")


class Currency(models.Model):
    full_name = models.CharField(max_length=96, blank=False, null=False, verbose_name="Full name")
    ticker = models.CharField(max_length=8, blank=False, null=False, verbose_name="Ticker")


# Create your models here.
class Thing(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True, blank=True)
    contract = models.ForeignKey("contracts.Contract", on_delete=models.CASCADE, null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=(
                    Q(material__isnull=False, contract__isnull=True, currency__isnull=True) |
                    Q(material__isnull=True, contract__isnull=False, currency__isnull=True) |
                    Q(material__isnull=True, contract__isnull=True, currency__isnull=False)
                ),
                name='mutual_exclusion_thing',
            ),
        ]

class Ownership(models.Model):
    corporation = models.ForeignKey("corporations.Corporation", on_delete=models.CASCADE, null=False, blank=False)
    thing  = models.ForeignKey(Thing, on_delete=models.CASCADE, null=False, blank=False)
    amount = models.DecimalField(max_digits=24, decimal_places=2)