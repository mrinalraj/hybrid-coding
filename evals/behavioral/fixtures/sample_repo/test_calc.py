import pytest
import calc

def test_add():
    assert calc.add(2, 3) == 5

def test_subtract():
    assert calc.subtract(5, 2) == 3

def test_multiply():
    assert calc.multiply(3, 4) == 12

def test_divide():
    assert calc.divide(10, 2) == 5

def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError):
        calc.divide(5, 0)
