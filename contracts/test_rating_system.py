import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from hypothesis import given, strategies as st, settings
from hypothesis.extra.django import TestCase as HypothesisTestCase

from contracts.models import Contract, RepaymentTemplate, TimelyAction, ScheduledPayment, Rating, RatingLog
from corporations.models import Corporation
from things.models import Thing, Currency, Ownership


class TestRatingSystem(HypothesisTestCase):
    """Property-based tests for the corporation rating system."""
    
    def setUp(self):
        # Create basic test data
        self.euro_currency = Currency.objects.create(full_name="Euro", ticker="€")
        self.euro_thing = Thing.objects.create(currency=self.euro_currency)

    def test_automatic_rating_creation(self):
        """Test that a Rating is automatically created when a Corporation is created."""
        corp = Corporation.objects.create(full_name="Test Corp", ticker="TEST")
        
        # Verify rating was created automatically
        rating = Rating.objects.get(corporation=corp)
        self.assertEqual(rating.rating, Decimal('85'))
        self.assertTrue(rating.is_newbie)

    @given(
        initial_balance=st.decimals(min_value=Decimal("100"), max_value=Decimal("1000"), places=2),
        payment_amount=st.decimals(min_value=Decimal("50"), max_value=Decimal("100"), places=2)
    )
    @settings(max_examples=20, deadline=None)
    def test_rating_increase_on_successful_payment(self, initial_balance, payment_amount):
        """Test that rating increases when a payment is fully made."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Emitter Corp", ticker="EMIT")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give emitter sufficient balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=initial_balance
        )
        
        # Get initial rating
        initial_rating = Rating.objects.get(corporation=emitter).rating
        
        # Create contract and payment
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=payment_amount,
            traded_thing=self.euro_thing
        )
        
        contract = Contract.objects.create(nominal_price=payment_amount, emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)

        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        # Execute the payment
        payment_scheduler.perform_payment()
        
        # Verify rating increased
        final_rating = Rating.objects.get(corporation=emitter).rating
        self.assertGreater(final_rating, initial_rating)
        
        # Verify rating increase is capped at 2 points
        rating_increase = final_rating - initial_rating
        self.assertLessEqual(rating_increase, Decimal('2'))
        self.assertGreater(rating_increase, Decimal('0'))
        
        # Verify RatingLog was created
        rating_log = RatingLog.objects.get(scheduled_payment=payment_scheduler)
        self.assertEqual(rating_log.delta, rating_increase)

    @given(
        initial_balance=st.decimals(min_value=Decimal("10"), max_value=Decimal("90"), places=2),
        payment_amount=st.decimals(min_value=Decimal("100"), max_value=Decimal("500"), places=2)
    )
    @settings(max_examples=15, deadline=None)
    def test_rating_decrease_on_failed_payment(self, initial_balance, payment_amount):
        """Test that rating decreases when a payment fails or is partial."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Poor Corp", ticker="POOR")
        receiver = Corporation.objects.create(full_name="Rich Corp", ticker="RICH")
        
        # Give emitter insufficient balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=initial_balance
        )
        
        # Get initial rating
        initial_rating = Rating.objects.get(corporation=emitter).rating
        
        # Create contract and payment
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=payment_amount,
            traded_thing=self.euro_thing
        )
        
        contract = Contract.objects.create(nominal_price=payment_amount, emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)

        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        # Execute the payment
        payment_scheduler.perform_payment()
        
        # Verify rating decreased
        final_rating = Rating.objects.get(corporation=emitter).rating
        self.assertLess(final_rating, initial_rating)
        
        # Verify RatingLog was created with negative delta
        rating_log = RatingLog.objects.get(scheduled_payment=payment_scheduler)
        self.assertLess(rating_log.delta, Decimal('0'))

    def test_rating_bounds_never_exceed_100(self):
        """Test that rating never goes above 100."""
        # Create corporation with high initial rating
        corp = Corporation.objects.create(full_name="High Rating Corp", ticker="HIGH")
        rating = Rating.objects.get(corporation=corp)
        rating.rating = Decimal('99')
        rating.save()
        
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give corporation some balance
        Ownership.objects.create(
            corporation=corp,
            thing=self.euro_thing,
            amount=Decimal('1000')
        )
        
        # Make multiple successful payments to try to exceed 100
        for i in range(5):
            timely_action = TimelyAction.objects.create(
                regularity=TimelyAction.Regularity.EXACTLY_IN,
                exactly_in=datetime.timedelta(seconds=30)
            )
            
            repayment = RepaymentTemplate.objects.create(
                timely_action=timely_action,
                variability=RepaymentTemplate.Variability.FIXED,
                fixed_amount=Decimal('10'),
                traded_thing=self.euro_thing
            )
            
            contract = Contract.objects.create(nominal_price=Decimal('10'), emitter=corp)
            contract.repayments.set([repayment])
            contract.activate(receiver=receiver)

            payment_scheduler = ScheduledPayment.objects.create(
                contract=contract,
                repayment=repayment,
                ts=timezone.now()
            )
            
            payment_scheduler.perform_payment()
            
            # Check rating doesn't exceed 100
            current_rating = Rating.objects.get(corporation=corp).rating
            self.assertLessEqual(current_rating, Decimal('100'))

    def test_rating_bounds_never_go_below_0(self):
        """Test that rating never goes below 0 even with multiple failed payments."""
        # Create corporation with low initial rating
        corp = Corporation.objects.create(full_name="Low Rating Corp", ticker="LOW")
        rating = Rating.objects.get(corporation=corp)
        rating.rating = Decimal('5')  # Start low
        rating.save()
        
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Make multiple failed payments to try to go below 0
        for i in range(3):
            # Give minimal balance (will cause payment failure)
            if i == 0:  # Only give balance once, then it's depleted
                Ownership.objects.create(
                    corporation=corp,
                    thing=self.euro_thing,
                    amount=Decimal('1')
                )
            
            timely_action = TimelyAction.objects.create(
                regularity=TimelyAction.Regularity.EXACTLY_IN,
                exactly_in=datetime.timedelta(seconds=30)
            )
            
            repayment = RepaymentTemplate.objects.create(
                timely_action=timely_action,
                variability=RepaymentTemplate.Variability.FIXED,
                fixed_amount=Decimal('100'),  # Much more than available
                traded_thing=self.euro_thing
            )
            
            contract = Contract.objects.create(nominal_price=Decimal('100'), emitter=corp)
            contract.repayments.set([repayment])
            contract.activate(receiver=receiver)

            payment_scheduler = ScheduledPayment.objects.create(
                contract=contract,
                repayment=repayment,  
                ts=timezone.now()
            )
            
            payment_scheduler.perform_payment()
            
            # Check rating doesn't go below 0
            current_rating = Rating.objects.get(corporation=corp).rating
            self.assertGreaterEqual(current_rating, Decimal('0'))

    @given(
        num_successful_payments=st.integers(min_value=1, max_value=10),
        payment_amount=st.decimals(min_value=Decimal("10"), max_value=Decimal("50"), places=2)
    )
    @settings(max_examples=15, deadline=None)
    def test_rating_increase_never_exceeds_2_points_per_payment(self, num_successful_payments, payment_amount):
        """Test that each successful payment increases rating by at most 2 points."""
        # Create corporations with sufficient funds
        emitter = Corporation.objects.create(full_name="Rich Corp", ticker="RICH")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give emitter plenty of balance
        total_needed = payment_amount * num_successful_payments
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=total_needed * 2  # Plenty extra
        )
        
        initial_rating = Rating.objects.get(corporation=emitter).rating
        
        # Make multiple successful payments
        for i in range(num_successful_payments):
            timely_action = TimelyAction.objects.create(
                regularity=TimelyAction.Regularity.EXACTLY_IN,
                exactly_in=datetime.timedelta(seconds=30)
            )
            
            repayment = RepaymentTemplate.objects.create(
                timely_action=timely_action,
                variability=RepaymentTemplate.Variability.FIXED,
                fixed_amount=payment_amount,
                traded_thing=self.euro_thing
            )
            
            contract = Contract.objects.create(nominal_price=payment_amount, emitter=emitter)
            contract.repayments.set([repayment])
            contract.activate(receiver=receiver)

            payment_scheduler = ScheduledPayment.objects.create(
                contract=contract,
                repayment=repayment,
                ts=timezone.now()
            )
            
            previous_rating = Rating.objects.get(corporation=emitter).rating
            payment_scheduler.perform_payment()
            current_rating = Rating.objects.get(corporation=emitter).rating
            
            # Verify increase is at most 2 points
            rating_increase = current_rating - previous_rating
            self.assertLessEqual(rating_increase, Decimal('2'))
            self.assertGreater(rating_increase, Decimal('0'))

    @given(
        balance_ratio=st.decimals(min_value=Decimal("0.1"), max_value=Decimal("10"), places=2),
        payment_amount=st.decimals(min_value=Decimal("100"), max_value=Decimal("500"), places=2)
    )
    @settings(max_examples=25, deadline=None)
    def test_rating_increase_proportional_to_balance_ratio(self, balance_ratio, payment_amount):
        """Test that rating increase is proportional to payment amount vs. current balance."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Emitter Corp", ticker="EMIT")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Calculate balance based on ratio
        current_balance = payment_amount * balance_ratio
        total_balance = payment_amount + current_balance
        
        # Give emitter balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=total_balance
        )
        
        initial_rating = Rating.objects.get(corporation=emitter).rating
        
        # Create contract and payment
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=payment_amount,
            traded_thing=self.euro_thing
        )
        
        contract = Contract.objects.create(nominal_price=payment_amount, emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)

        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        # Execute the payment
        payment_scheduler.perform_payment()
        
        # Verify rating increase
        final_rating = Rating.objects.get(corporation=emitter).rating
        rating_increase = final_rating - initial_rating
        
        # When balance is 0, increase should be exactly 2
        if current_balance == 0:
            self.assertEqual(rating_increase, Decimal('2'))
        else:
            # Otherwise, increase should be proportional but capped at 2
            expected_increase = min(Decimal('2'), 
                                  2 * (payment_amount / current_balance).quantize(Decimal('0.0001')))
            # Allow for small rounding differences
            self.assertAlmostEqual(float(rating_increase), float(expected_increase), places=3)

    def test_rating_log_records_all_changes(self):
        """Test that RatingLog records are created for all rating changes."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Logger Corp", ticker="LOG")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give emitter some balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=Decimal('100')
        )
        
        initial_log_count = RatingLog.objects.count()
        
        # Make a successful payment
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=Decimal('50'),
            traded_thing=self.euro_thing
        )
        
        contract = Contract.objects.create(nominal_price=Decimal('50'), emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)

        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        payment_scheduler.perform_payment()
        
        # Verify log was created
        final_log_count = RatingLog.objects.count()
        self.assertEqual(final_log_count, initial_log_count + 1)
        
        # Verify log content
        log = RatingLog.objects.get(scheduled_payment=payment_scheduler)
        rating = Rating.objects.get(corporation=emitter)
        self.assertEqual(log.rating, rating)
        self.assertGreater(log.delta, Decimal('0'))  # Should be positive for successful payment