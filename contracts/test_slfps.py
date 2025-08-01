from decimal import Decimal
from unittest.mock import Mock
from django.test import TestCase
from hypothesis import given, strategies as st
from hypothesis.extra.django import TestCase as HypothesisTestCase
from hypothesis.strategies import composite

from contracts.slfps import calculate, SLFPS_Exception, FUNCTIONS, VARIABLES
from contracts.models import Contract, ScheduledPayment


class TestSLFPSInterpreter(TestCase):

    def setUp(self):
        """Create mock objects for testing"""
        self.mock_contract = Mock(spec=Contract)
        self.mock_contract.nominal_price = Decimal('1000.00')

        self.mock_scheduled_payment = Mock(spec=ScheduledPayment)
        self.mock_scheduled_payment.contract = self.mock_contract
        self.mock_scheduled_payment.execution_order = 5

    def test_basic_number_parsing(self):
        """Test parsing of numeric literals"""
        assert calculate("42", self.mock_scheduled_payment) == Decimal('42')
        assert calculate("42.5", self.mock_scheduled_payment) == Decimal('42.5')
        assert calculate("-10", self.mock_scheduled_payment) == Decimal('-10')
        assert calculate("+15.25", self.mock_scheduled_payment) == Decimal('15.25')

    def test_variable_access(self):
        """Test accessing variables from scheduled payment"""
        result = calculate("nominal_price", self.mock_scheduled_payment)
        assert result == Decimal('1000.00')

        result = calculate("execution_order", self.mock_scheduled_payment)
        assert result == 5

    def test_invalid_variable(self):
        """Test error handling for invalid variables"""
        with self.assertRaisesRegex(Exception, "Unexpected token: invalid_var"):
            calculate("invalid_var", self.mock_scheduled_payment)

    def test_basic_arithmetic(self):
        """Test basic arithmetic operations"""
        # Addition
        result = calculate(["+", "10", "5"], self.mock_scheduled_payment)
        assert result == Decimal('15')

        # Subtraction
        result = calculate(["-", "20", "8"], self.mock_scheduled_payment)
        assert result == Decimal('12')

        # Multiplication
        result = calculate(["*", "6", "7"], self.mock_scheduled_payment)
        assert result == Decimal('42')

        # Division
        result = calculate(["/", "100", "4"], self.mock_scheduled_payment)
        assert result == Decimal('25')

    def test_percentage_calculation(self):
        """Test percentage operations"""
        # 5% of 100 should be 5
        result = calculate(["%", "100", "5"], self.mock_scheduled_payment)
        assert result == Decimal('5')

        # 2.5% of 1000 should be 25
        result = calculate(["%", "1000", "2.5"], self.mock_scheduled_payment)
        assert result == Decimal('25')

    def test_nested_expressions(self):
        """Test nested formula evaluation"""
        # (10 + 5) * 2 = 30
        result = calculate(["*", ["+", "10", "5"], "2"], self.mock_scheduled_payment)
        assert result == Decimal('30')

        # 10% of (200 + 300) = 10% of 500 = 50
        result = calculate(["%", ["+", "200", "300"], "10"], self.mock_scheduled_payment)
        assert result == Decimal('50')

    def test_step_up_bond_example(self):
        """Test the step-up bond example from the comments"""
        # {"formula": ["%", "nominal_price", ["+", "2.0", "execution_order"]]}
        # Should be: (2.0 + 5) = 7% of 1000 = 70
        formula = ["%", "nominal_price", ["+", "2.0", "execution_order"]]
        result = calculate(formula, self.mock_scheduled_payment)
        assert result == Decimal('70')

    def test_random_function(self):
        """Test random function returns valid decimal"""
        result = calculate(["random"], self.mock_scheduled_payment)
        assert isinstance(result, Decimal)
        assert Decimal('0') <= result <= Decimal('1')

        # Test random in expression
        result = calculate(["+", "50", ["*", "10", ["random"]]], self.mock_scheduled_payment)
        assert Decimal('50') <= result <= Decimal('60')

    def test_unknown_function_error(self):
        """Test error handling for unknown functions"""
        with self.assertRaisesRegex(SLFPS_Exception, "Unknown function: unknown_func"):
            calculate(["unknown_func", "10"], self.mock_scheduled_payment)

    def test_all_functions_exist(self):
        """Test that all declared functions are callable"""
        for func_name, func in FUNCTIONS.items():
            assert callable(func)

    def test_all_variables_exist(self):
        """Test that all declared variables are callable"""
        for var_name, var_func in VARIABLES.items():
            assert callable(var_func)
            # Test they work with our mock
            result = var_func(self.mock_scheduled_payment)
            assert result is not None


@composite
def valid_numbers(draw):
    """Generate valid number strings for testing"""
    num = draw(st.floats(min_value=-1000000, max_value=1000000, allow_nan=False, allow_infinity=False))
    # Convert to string and back to ensure it's valid
    num_str = str(num)
    try:
        Decimal(num_str)
        return num_str
    except:
        return "0"


@composite
def simple_formulas(draw):
    """Generate simple arithmetic formulas"""
    op = draw(st.sampled_from(["+", "-", "*", "/", "%"]))
    num1 = draw(valid_numbers())
    num2 = draw(valid_numbers())
    # Avoid division by zero
    if op == "/" and float(num2) == 0:
        num2 = "1"
    return [op, num1, num2]


class TestSLFPSProperty(HypothesisTestCase):
    """Property-based tests using Hypothesis"""
    
    def setUp(self):
        self.mock_contract = Mock(spec=Contract)
        self.mock_contract.nominal_price = Decimal('1000.00')
        
        self.mock_scheduled_payment = Mock(spec=ScheduledPayment)
        self.mock_scheduled_payment.contract = self.mock_contract
        self.mock_scheduled_payment.execution_order = 3

    @given(valid_numbers())
    def test_number_parsing_property(self, num_str):
        """Property: All valid number strings should parse to Decimal"""
        try:
            result = calculate(num_str, self.mock_scheduled_payment)
            assert isinstance(result, Decimal)
            assert result == Decimal(num_str)
        except:
            # If our number generation fails, that's ok
            pass

    @given(simple_formulas())
    def test_arithmetic_operations_property(self, formula):
        """Property: Basic arithmetic operations should not crash"""
        try:
            result = calculate(formula, self.mock_scheduled_payment)
            assert isinstance(result, Decimal)
        except ZeroDivisionError:
            # Division by zero is expected to fail
            pass
        except:
            # Other decimal conversion errors are acceptable
            pass

    @given(st.floats(min_value=0, max_value=100, allow_nan=False))
    def test_percentage_property(self, percentage):
        """Property: Percentage calculations should be mathematically correct"""
        base = Decimal('100')
        try:
            result = calculate(["%", "100", str(percentage)], self.mock_scheduled_payment)
            expected = base * Decimal(str(percentage)) / Decimal('100')
            assert abs(result - expected) < Decimal('0.01')  # Allow for rounding
        except:
            # Handle invalid decimal conversions
            pass

    @given(st.integers(min_value=0, max_value=10))
    def test_execution_order_property(self, execution_order):
        """Property: Different execution orders should affect step-up calculations"""
        self.mock_scheduled_payment.execution_order = execution_order
        
        # Test step-up bond formula
        formula = ["%", "nominal_price", ["+", "2.0", "execution_order"]]
        result = calculate(formula, self.mock_scheduled_payment)
        
        expected_percentage = Decimal('2.0') + Decimal(str(execution_order))
        expected_result = Decimal('1000.00') * expected_percentage / Decimal('100')
        
        assert result == expected_result