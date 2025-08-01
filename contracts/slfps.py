# Simplified Language for Payment Specification

## Examples
"""
;; obbligazioni step-up
{"formula": ["%", "nominal_price", ["+", "2.0", "execution_order"]]} ==> [%, X, Y] means: Y% of X, where X is a number between 0 and 100

;; lottery
{"formula": ["+", "50", ["*", "10", ["random"]]]}
"""
import decimal
import random
import re
from decimal import Decimal

from utils.calculations import percent

# Note: ScheduledPayment type is used as parameter but imported at runtime to avoid circular imports

is_number_regex = re.compile(r"[\-\+]?[0-9]+(\.[0-9]+)?")

FUNCTIONS = {
    "+": lambda x,y: x+y,
    "-": lambda x,y: x-y,
    "*": lambda x,y: x*y,
    "/": lambda x,y: x/y,
    "%": lambda whole,perc: percent(whole, perc),
    "random": lambda: Decimal(random.random()).quantize(Decimal('.0001'), rounding=decimal.ROUND_DOWN)
}
NON_PREDICTABLE_FUNCTIONS = ["random"]

VARIABLES = {
    "nominal_price": lambda sp: sp.contract.nominal_price,
    "execution_order": lambda sp: sp.execution_order
}

class SLFPS_Exception(Exception):
    pass

def calculate(formula: list|str, scheduled_payment: "ScheduledPayment") -> Decimal:
    if isinstance(formula, str):
        if re.fullmatch(is_number_regex, formula):
            return Decimal(formula)
        if formula in VARIABLES:
            return VARIABLES[formula](scheduled_payment)
        raise Exception(f"Unexpected token: {formula}")

    function_name, *args = formula
    if function_name not in FUNCTIONS:
        raise SLFPS_Exception(f"Unknown function: {function_name}")

    return FUNCTIONS[function_name](*[calculate(arg, scheduled_payment) for arg in args])

