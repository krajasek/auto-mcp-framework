"""Simple math utilities to demonstrate auto-mcp tool generation.

This module contains basic mathematical operations that will be
automatically exposed as MCP tools when processed by auto-mcp.
"""

from __future__ import annotations


def add(a: float, b: float) -> float:
    """Add two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        The sum of a and b
    """
    return a + b


def subtract(a: float, b: float) -> float:
    """Subtract the second number from the first.

    Args:
        a: Number to subtract from
        b: Number to subtract

    Returns:
        The difference (a - b)
    """
    return a - b


def multiply(a: float, b: float) -> float:
    """Multiply two numbers together.

    Args:
        a: First number
        b: Second number

    Returns:
        The product of a and b
    """
    return a * b


def divide(a: float, b: float) -> float:
    """Divide the first number by the second.

    Args:
        a: Dividend (number to divide)
        b: Divisor (number to divide by)

    Returns:
        The quotient (a / b)

    Raises:
        ZeroDivisionError: If b is zero
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b


def power(base: float, exponent: float) -> float:
    """Raise a number to a power.

    Args:
        base: The base number
        exponent: The power to raise to

    Returns:
        base raised to the power of exponent
    """
    return base**exponent


def factorial(n: int) -> int:
    """Calculate the factorial of a non-negative integer.

    Args:
        n: A non-negative integer

    Returns:
        n! (n factorial)

    Raises:
        ValueError: If n is negative
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    if n <= 1:
        return 1
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result


def is_prime(n: int) -> bool:
    """Check if a number is prime.

    Args:
        n: The number to check

    Returns:
        True if n is prime, False otherwise
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    return all(n % i != 0 for i in range(3, int(n**0.5) + 1, 2))


def gcd(a: int, b: int) -> int:
    """Calculate the greatest common divisor of two integers.

    Uses Euclid's algorithm.

    Args:
        a: First integer
        b: Second integer

    Returns:
        The greatest common divisor of a and b
    """
    a, b = abs(a), abs(b)
    while b:
        a, b = b, a % b
    return a


def _internal_helper() -> None:
    """This private function will not be exposed as a tool."""
    pass
