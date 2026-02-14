"""Pure-function rules engine pattern.

Rules are stateless functions: (entity, context) -> RuleResult.
No database, no side effects, no LLM calls. This makes them:
- Trivially testable (pure input/output)
- Composable (chain multiple rules)
- Auditable (deterministic, explainable)

Example domain: a bookstore checking discount eligibility and stock levels.
"""

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Outcome of a single rule evaluation."""

    passed: bool
    rule_name: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleSetResult:
    """Aggregate outcome of multiple rules."""

    all_passed: bool
    results: list[RuleResult]
    failed: list[RuleResult] = field(default_factory=list)

    def __post_init__(self):
        self.failed = [r for r in self.results if not r.passed]
        self.all_passed = len(self.failed) == 0


# ---------------------------------------------------------------------------
# Example rules (bookstore domain)
# ---------------------------------------------------------------------------

def check_stock_availability(item: dict, quantity: int = 1) -> RuleResult:
    """Check if an item has sufficient stock.

    Pure function: takes item dict + requested quantity, returns result.
    """
    available = item.get("stock_quantity", 0)
    passed = available >= quantity

    return RuleResult(
        passed=passed,
        rule_name="stock_availability",
        message=(
            f"In stock: {available} available"
            if passed
            else f"Insufficient stock: {available} available, {quantity} requested"
        ),
        details={"available": available, "requested": quantity},
    )


def check_discount_eligibility(
    customer: dict,
    order_total: float,
    min_order: float = 50.0,
    min_loyalty_points: int = 100,
) -> RuleResult:
    """Check if a customer qualifies for a discount.

    Rules:
    - Order must exceed minimum threshold
    - Customer must have sufficient loyalty points
    """
    points = customer.get("loyalty_points", 0)
    meets_order = order_total >= min_order
    meets_loyalty = points >= min_loyalty_points
    passed = meets_order and meets_loyalty

    reasons = []
    if not meets_order:
        reasons.append(f"Order total ${order_total:.2f} below ${min_order:.2f} minimum")
    if not meets_loyalty:
        reasons.append(f"{points} loyalty points below {min_loyalty_points} minimum")

    return RuleResult(
        passed=passed,
        rule_name="discount_eligibility",
        message="Eligible for discount" if passed else "; ".join(reasons),
        details={
            "order_total": order_total,
            "loyalty_points": points,
            "meets_order_threshold": meets_order,
            "meets_loyalty_threshold": meets_loyalty,
        },
    )


def check_return_eligibility(
    order: dict,
    days_since_purchase: int,
    max_return_days: int = 30,
) -> RuleResult:
    """Check if an order is eligible for return."""
    within_window = days_since_purchase <= max_return_days
    is_returnable = order.get("is_returnable", True)
    passed = within_window and is_returnable

    reasons = []
    if not within_window:
        reasons.append(f"{days_since_purchase} days exceeds {max_return_days}-day window")
    if not is_returnable:
        reasons.append("Item marked as non-returnable")

    return RuleResult(
        passed=passed,
        rule_name="return_eligibility",
        message="Eligible for return" if passed else "; ".join(reasons),
        details={
            "days_since_purchase": days_since_purchase,
            "max_return_days": max_return_days,
            "is_returnable": is_returnable,
        },
    )


# ---------------------------------------------------------------------------
# Rule composition
# ---------------------------------------------------------------------------

def evaluate_rules(*rules: RuleResult) -> RuleSetResult:
    """Compose multiple rule results into a single aggregate.

    Example::

        result = evaluate_rules(
            check_stock_availability(item, qty=2),
            check_discount_eligibility(customer, order_total=75.0),
        )
        if result.all_passed:
            apply_discount(order)
    """
    return RuleSetResult(
        all_passed=all(r.passed for r in rules),
        results=list(rules),
    )
