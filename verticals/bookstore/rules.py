"""Bookstore business rules — pure functions.

Re-exports and extends the rules engine pattern with bookstore-specific rules.
"""

from patterns.rules_engine import (
    RuleResult,
    RuleSetResult,
    check_stock_availability,
    check_discount_eligibility,
    check_return_eligibility,
    evaluate_rules,
)

__all__ = [
    "RuleResult",
    "RuleSetResult",
    "check_stock_availability",
    "check_discount_eligibility",
    "check_return_eligibility",
    "evaluate_rules",
]
