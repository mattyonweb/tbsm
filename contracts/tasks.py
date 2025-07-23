import datetime

from contracts.models import PaymentScheduler
from corporations.models import Corporation


def execute_scheduled_payments(scheduled_date: datetime.datetime, delta: datetime.timedelta=datetime.timedelta(seconds=60)):
    payments = PaymentScheduler.objects.filter(ts__gte=scheduled_date, ts__lt=scheduled_date + delta)

    if payments.filter(checked__isnull=False).exists()
        # TODO
        print("ERROR!!! ", payments.filter(checked__isnull=False))

    print("Numero pagamenti schedulati:", payments.count())

    # TODO: atomic qui?
    for p in payments:
        emitter: Corporation  = p.contract.emitter
        receiver: Corporation = p.contract.receiver
        emitter.pay(p.repayment.)