import datetime
from contracts.models import PaymentScheduler


def execute_scheduled_payments(scheduled_date: datetime.datetime, delta: datetime.timedelta=datetime.timedelta(seconds=60)):
    """
    Execute scheduled payments that are due within the specified time window.
    
    Args:
        scheduled_date: The current time to check payments against
        delta: Time window to look ahead for payments (default 60 seconds)
    """
    # Get all payments scheduled within the time window that haven't been checked yet
    payments = PaymentScheduler.objects.filter(
        ts__gte=scheduled_date, 
        ts__lt=scheduled_date + delta,
        checked=False
    )

    # Check if there are any payments that were already checked (shouldn't happen)
    already_checked = PaymentScheduler.objects.filter(
        ts__gte=scheduled_date,
        ts__lt=scheduled_date + delta,
        checked=True
    )

    # Check if there are any payments that were already checked (shouldn't happen)
    should_have_been_checked = PaymentScheduler.objects.filter(
        ts__gte=scheduled_date - delta,
        ts__lt=scheduled_date,
        checked=True
    )

    if already_checked.exists():
        print(f"WARNING: Found {already_checked.count()} payments already checked in this time window")
    if should_have_been_checked:
        print(f"WARNING: Found {already_checked.count()} payments that should have been already checked in this time window")

    print(f"Numero pagamenti schedulati: {payments.count()}")

    # Process each payment atomically
    for payment in payments:
        payment.perform_payment()