from django.contrib import admin

from contracts.models import TimelyAction, RepaymentTemplate, Contract, ScheduledPayment

# Register your models here.

admin.site.register(TimelyAction)
admin.site.register(RepaymentTemplate)
admin.site.register(Contract)
admin.site.register(ScheduledPayment)