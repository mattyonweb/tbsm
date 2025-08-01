import datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from hypothesis import given, strategies as st, settings
from hypothesis.extra.django import TestCase as HypothesisTestCase

from accounts.models import CustomUser
from contracts.models import Contract, RepaymentTemplate, TimelyAction, ScheduledPayment
from corporations.models import Corporation
from things.models import Thing, Currency, Material, Ownership
from utils.calculations import percent


class TestPaymentExecution(HypothesisTestCase):
    """Property-based tests using Hypothesis for payment execution focused on perform_payment() method."""
    
    def setUp(self):
        # Create basic test data
        self.euro_currency = Currency.objects.create(full_name="Euro", ticker="€")
        self.euro_thing = Thing.objects.create(currency=self.euro_currency)
        
        self.gold_material = Material.objects.create(full_name="Gold", ticker="AU")
        self.gold_thing = Thing.objects.create(material=self.gold_material)

    @staticmethod
    @st.composite
    def corporation_strategy(draw):
        """Generate a Corporation with random but valid data."""
        full_name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pc', 'Pd', 'Zs'))))
        ticker = draw(st.text(min_size=1, max_size=8, alphabet=st.characters(whitelist_categories=('Lu', 'Nd'))))
        return Corporation.objects.create(full_name=full_name, ticker=ticker)

    @given(
        emitter_balance=st.decimals(min_value=Decimal("100"), max_value=Decimal("10000"), places=2),
        payment_amount=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=2),
        receiver_initial_balance=st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"), places=2)
    )
    @settings(max_examples=20, deadline=None)
    def test_perform_payment_sufficient_funds(self, emitter_balance, payment_amount, receiver_initial_balance):
        """Test perform_payment() when emitter has sufficient funds."""
        # Ensure payment is affordable
        payment_amount = min(payment_amount, emitter_balance)
        
        # Create corporations
        emitter = Corporation.objects.create(full_name="Emitter Corp", ticker="EMIT")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give emitter balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=emitter_balance
        )
        
        # Give receiver initial balance if any
        if receiver_initial_balance > 0:
            Ownership.objects.create(
                corporation=receiver,
                thing=self.euro_thing,
                amount=receiver_initial_balance
            )
        
        # Create contract and payment scheduler
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

        # Create payment scheduler directly (skip activation timing logic)
        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now() #timezone.now()
        )
        
        # Execute the payment
        payment_scheduler.perform_payment()
        
        # Verify payment was processed successfully
        payment_scheduler.refresh_from_db()
        self.assertTrue(payment_scheduler.was_processed)
        self.assertTrue(payment_scheduler.paid)
        self.assertFalse(payment_scheduler.missed_payment)
        
        # Verify ownership transfer
        emitter_ownership = Ownership.objects.filter(corporation=emitter, thing=self.euro_thing).first()
        receiver_ownership = Ownership.objects.filter(corporation=receiver, thing=self.euro_thing).first()
        
        expected_emitter_balance = emitter_balance - payment_amount
        expected_receiver_balance = receiver_initial_balance + payment_amount
        
        if expected_emitter_balance > 0:
            self.assertIsNotNone(emitter_ownership)
            self.assertEqual(emitter_ownership.amount, expected_emitter_balance)
        else:
            self.assertIsNone(emitter_ownership)
        
        self.assertIsNotNone(receiver_ownership)
        self.assertEqual(receiver_ownership.amount, expected_receiver_balance)

    @given(
        emitter_balance=st.decimals(min_value=Decimal("1"), max_value=Decimal("99"), places=2),
        payment_amount=st.decimals(min_value=Decimal("100"), max_value=Decimal("1000"), places=2)
    )
    @settings(max_examples=15, deadline=None)
    def test_perform_payment_insufficient_funds(self, emitter_balance, payment_amount):
        """Test perform_payment() when emitter has insufficient funds."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Poor Corp", ticker="POOR")
        receiver = Corporation.objects.create(full_name="Rich Corp", ticker="RICH")
        
        # Give emitter insufficient balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=emitter_balance
        )
        
        # Create contract and payment scheduler
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
        
        # Verify payment was processed but not fully paid
        payment_scheduler.refresh_from_db()
        self.assertTrue(payment_scheduler.was_processed)
        self.assertFalse(payment_scheduler.paid)
        self.assertTrue(payment_scheduler.missed_payment)
        
        # Verify corporation went bankrupt
        emitter.refresh_from_db()
        self.assertIsNotNone(emitter.bankrupt)
        
        # Verify all available funds were transferred
        emitter_ownership = Ownership.objects.filter(corporation=emitter, thing=self.euro_thing).first()
        receiver_ownership = Ownership.objects.filter(corporation=receiver, thing=self.euro_thing).first()
        
        self.assertIsNone(emitter_ownership)  # Should have no money left
        self.assertIsNotNone(receiver_ownership)
        self.assertEqual(receiver_ownership.amount, emitter_balance)  # Received whatever emitter had

    @given(
        emitter_balance=st.decimals(min_value=Decimal("50"), max_value=Decimal("1000"), places=2),
        payment_amount=st.decimals(min_value=Decimal("1"), max_value=Decimal("100"), places=2)
    )
    @settings(max_examples=15, deadline=None)
    def test_perform_payment_different_things(self, emitter_balance, payment_amount):
        """Test perform_payment() with different types of traded things (gold instead of currency)."""
        # Ensure payment is affordable
        payment_amount = min(payment_amount, emitter_balance)
        
        # Create corporations
        emitter = Corporation.objects.create(full_name="Gold Corp", ticker="GOLD")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        # Give emitter gold
        Ownership.objects.create(
            corporation=emitter,
            thing=self.gold_thing,
            amount=emitter_balance
        )
        
        # Create contract paying in gold
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=payment_amount,
            traded_thing=self.gold_thing
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
        
        # Verify payment was processed successfully
        payment_scheduler.refresh_from_db()
        self.assertTrue(payment_scheduler.was_processed)
        self.assertTrue(payment_scheduler.paid)
        self.assertFalse(payment_scheduler.missed_payment)
        
        # Verify gold transfer
        emitter_gold = Ownership.objects.filter(corporation=emitter, thing=self.gold_thing).first()
        receiver_gold = Ownership.objects.filter(corporation=receiver, thing=self.gold_thing).first()
        
        expected_emitter_gold = emitter_balance - payment_amount
        if expected_emitter_gold > 0:
            self.assertIsNotNone(emitter_gold)
            self.assertEqual(emitter_gold.amount, expected_emitter_gold)
        else:
            self.assertIsNone(emitter_gold)
        
        self.assertIsNotNone(receiver_gold)
        self.assertEqual(receiver_gold.amount, payment_amount)

    @given(
        emitter=corporation_strategy(),
        receiver=corporation_strategy(),
        payment_amounts=st.lists(
            st.decimals(min_value=Decimal("10"), max_value=Decimal("100"), places=2),
            min_size=2, max_size=5
        ),
        initial_balance=st.decimals(min_value=Decimal("1000"), max_value=Decimal("5000"), places=2)
    )
    @settings(max_examples=70, deadline=None)
    def test_multiple_payments_from_same_contract(self, emitter, receiver, payment_amounts, initial_balance):
        """Test multiple payments from the same contract to verify cumulative exchanges."""

        # Ensure emitter has enough for all payments
        total_payments = sum(payment_amounts)
        if total_payments > initial_balance:
            return  # Skip this test case
            
        # Give emitter initial balance
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=initial_balance
        )
        
        # Create contract
        contract = Contract.objects.create(nominal_price=total_payments, emitter=emitter)
        contract.activate(receiver=receiver)

        # Create multiple payment schedulers for the same contract
        payment_schedulers = []
        for payment_amount in payment_amounts:
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
            
            payment_scheduler = ScheduledPayment.objects.create(
                contract=contract,
                repayment=repayment,
                ts=timezone.now()
            )
            payment_schedulers.append(payment_scheduler)
        
        # Execute all payments
        for payment_scheduler in payment_schedulers:
            payment_scheduler.perform_payment()
        
        # Verify all payments were processed successfully
        for payment_scheduler in payment_schedulers:
            payment_scheduler.refresh_from_db()
            self.assertTrue(payment_scheduler.was_processed)
            self.assertTrue(payment_scheduler.paid)
            self.assertFalse(payment_scheduler.missed_payment)
        
        # Verify final balances
        emitter_ownership = Ownership.objects.filter(corporation=emitter, thing=self.euro_thing).first()
        receiver_ownership = Ownership.objects.filter(corporation=receiver, thing=self.euro_thing).first()
        
        expected_emitter_balance = initial_balance - total_payments
        expected_receiver_balance = total_payments
        
        if expected_emitter_balance > 0:
            self.assertIsNotNone(emitter_ownership)
            self.assertEqual(emitter_ownership.amount, expected_emitter_balance)
        else:
            self.assertIsNone(emitter_ownership)
        
        self.assertIsNotNone(receiver_ownership)
        self.assertEqual(receiver_ownership.amount, expected_receiver_balance)

    def test_perform_payment_no_receiver(self):
        """Test that perform_payment() raises exception when contract has no receiver."""
        emitter = Corporation.objects.create(full_name="Emitter Corp", ticker="EMIT")
        
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=Decimal("1000")
        )
        
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=Decimal("100"),
            traded_thing=self.euro_thing
        )
        
        # Create contract without receiver
        contract = Contract.objects.create(nominal_price=Decimal("100"), emitter=emitter)
        contract.repayments.set([repayment])
        
        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        # Should raise exception
        with self.assertRaises(Exception) as context:
            payment_scheduler.perform_payment()
        
        self.assertIn("Contract was not activated", str(context.exception))

    def test_perform_payment_idempotency(self):
        """Test that calling perform_payment() multiple times doesn't cause issues."""
        emitter = Corporation.objects.create(full_name="Emitter Corp", ticker="EMIT")
        receiver = Corporation.objects.create(full_name="Receiver Corp", ticker="RECV")
        
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=Decimal("1000")
        )
        
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EXACTLY_IN,
            exactly_in=datetime.timedelta(seconds=30)
        )
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.FIXED,
            fixed_amount=Decimal("100"),
            traded_thing=self.euro_thing
        )
        
        contract = Contract.objects.create(nominal_price=Decimal("100"), emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)

        payment_scheduler = ScheduledPayment.objects.create(
            contract=contract,
            repayment=repayment,
            ts=timezone.now()
        )
        
        # Execute payment twice
        payment_scheduler.perform_payment()
        initial_receiver_balance = Ownership.objects.get(corporation=receiver, thing=self.euro_thing).amount
        initial_emitter_balance = Ownership.objects.get(corporation=emitter, thing=self.euro_thing).amount
        
        # Second call should not change anything since was_processed is already True
        payment_scheduler.perform_payment()
        
        # Verify balances didn't change
        final_receiver_balance = Ownership.objects.get(corporation=receiver, thing=self.euro_thing).amount
        final_emitter_balance = Ownership.objects.get(corporation=emitter, thing=self.euro_thing).amount
        
        self.assertEqual(initial_receiver_balance, final_receiver_balance)
        self.assertEqual(initial_emitter_balance, final_emitter_balance)

    @given(
        nominal_price=st.decimals(min_value=Decimal("1000"), max_value=Decimal("10000"), places=2),
        initial_coupon_rate=st.decimals(min_value=Decimal("1.5"), max_value=Decimal("3.0"), places=2),
        coupon_increase=st.decimals(min_value=Decimal("0.25"), max_value=Decimal("1.0"), places=2),
        num_payments=st.integers(min_value=2, max_value=6),
        emitter_balance_multiplier=st.decimals(min_value=Decimal("2"), max_value=Decimal("5"), places=2)
    )
    @settings(max_examples=20, deadline=2000)
    def test_step_up_bond_variable_payments(self, nominal_price, initial_coupon_rate, coupon_increase, num_payments, emitter_balance_multiplier):
        """Test step-up bond with variable coupon payments using SLFPS formulas."""
        # Create corporations
        emitter = Corporation.objects.create(full_name="Bond Issuer", ticker="BOND")
        receiver = Corporation.objects.create(full_name="Bond Buyer", ticker="BUYR")
        
        # Calculate total expected payments to ensure sufficient funding
        total_expected = Decimal('0')
        for i in range(num_payments):
            coupon_rate = initial_coupon_rate + (coupon_increase * i)
            payment = (nominal_price * coupon_rate / Decimal('100.00')).quantize(Decimal('0.01'))
            total_expected += payment
        
        # Give emitter sufficient balance
        initial_balance = total_expected * emitter_balance_multiplier
        Ownership.objects.create(
            corporation=emitter,
            thing=self.euro_thing,
            amount=initial_balance
        )
        
        # Create timely action for multiple payments
        timely_action = TimelyAction.objects.create(
            regularity=TimelyAction.Regularity.EVERY,
            every=datetime.timedelta(days=90),  # Quarterly payments
            repeat_times=num_payments
        )
        
        # Create variable repayment template with step-up formula
        # Formula: nominal_price * (initial_rate + (increase * execution_order)) / 100
        step_up_formula = [
            "%",
            "nominal_price",
            ["+", str(initial_coupon_rate), ["*", str(coupon_increase), "execution_order"]]
        ]
        
        repayment = RepaymentTemplate.objects.create(
            timely_action=timely_action,
            variability=RepaymentTemplate.Variability.VARIABLE,
            variable_amount={"formula": step_up_formula},
            traded_thing=self.euro_thing
        )
        
        # Create and activate contract
        contract = Contract.objects.create(nominal_price=nominal_price, emitter=emitter)
        contract.repayments.set([repayment])
        contract.activate(receiver=receiver)
        
        # Get all scheduled payments created by activation
        scheduled_payments = ScheduledPayment.objects.filter(contract=contract).order_by('execution_order')
        
        # Verify correct number of payments were created
        self.assertEqual(len(scheduled_payments), num_payments)
        
        # Execute all payments and verify step-up behavior
        total_transferred = Decimal('0')
        for i, payment in enumerate(scheduled_payments):
            # Calculate expected amount for this payment
            expected_coupon_rate = initial_coupon_rate + (coupon_increase * i)
            expected_amount = percent(nominal_price, expected_coupon_rate)
            
            # Test absolutize_amount calculation
            calculated_amount = payment.absolutize_amount()
            self.assertEqual(calculated_amount, expected_amount)
            
            # Execute the payment
            payment.perform_payment()
            
            # Verify payment was successful
            payment.refresh_from_db()
            self.assertTrue(payment.was_processed)
            self.assertTrue(payment.paid)
            self.assertFalse(payment.missed_payment)
            
            total_transferred += expected_amount
        
        # Verify final balances
        emitter_ownership = Ownership.objects.filter(corporation=emitter, thing=self.euro_thing).first()
        receiver_ownership = Ownership.objects.filter(corporation=receiver, thing=self.euro_thing).first()
        
        expected_emitter_balance = initial_balance - total_transferred
        expected_receiver_balance = total_transferred
        
        if expected_emitter_balance > 0:
            self.assertIsNotNone(emitter_ownership)
            self.assertAlmostEqual(emitter_ownership.amount, expected_emitter_balance.quantize(Decimal("1.00")), 2)
        else:
            self.assertIsNone(emitter_ownership)
        
        self.assertIsNotNone(receiver_ownership)
        self.assertAlmostEqual(receiver_ownership.amount, expected_receiver_balance.quantize(Decimal("1.00")), 2)
        
        # Verify that coupon rates actually increased over time
        if num_payments > 1:
            first_payment_amount = scheduled_payments[0].absolutize_amount()
            last_payment_amount = scheduled_payments[num_payments-1].absolutize_amount()
            self.assertGreater(last_payment_amount, first_payment_amount)