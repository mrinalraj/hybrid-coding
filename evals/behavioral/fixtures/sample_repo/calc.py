"""Simple calculator library used as fixture for hybrid-coding evals."""

def add(a: float, b: float) -> float:
    return a + b

def subtract(a: float, b: float) -> float:
    return a - b

def multiply(a: float, b: float) -> float:
    return a * b

def divide(a: float, b: float) -> float:
    # Deliberate bug for eval scenario: doesn't handle 0 cleanly or raises wrong error
    if b == 0:
        return 0  # Bug: should raise ZeroDivisionError("division by zero")
    return a / b
