"""Enum-based workflow state machine pattern.

Defines workflow states as Python enums with explicit transition validation.
This pattern works with Temporal, Celery, or any task orchestrator — the
state definitions are independent of the execution engine.

Example domain: order fulfillment lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------

class OrderState(str, Enum):
    """Order fulfillment workflow states."""

    CREATED = "created"
    PAYMENT_PENDING = "payment_pending"
    PAYMENT_CONFIRMED = "payment_confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# ---------------------------------------------------------------------------
# Transition rules
# ---------------------------------------------------------------------------

# Allowed transitions: {current_state: [allowed_next_states]}
_ORDER_TRANSITIONS: dict[OrderState, list[OrderState]] = {
    OrderState.CREATED: [OrderState.PAYMENT_PENDING, OrderState.CANCELLED],
    OrderState.PAYMENT_PENDING: [OrderState.PAYMENT_CONFIRMED, OrderState.CANCELLED],
    OrderState.PAYMENT_CONFIRMED: [OrderState.PROCESSING, OrderState.CANCELLED],
    OrderState.PROCESSING: [OrderState.SHIPPED, OrderState.CANCELLED],
    OrderState.SHIPPED: [OrderState.DELIVERED],
    OrderState.DELIVERED: [OrderState.REFUNDED],
    OrderState.CANCELLED: [],  # terminal
    OrderState.REFUNDED: [],   # terminal
}


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@dataclass
class WorkflowTransition:
    """Record of a single state transition."""

    from_state: str
    to_state: str
    timestamp: datetime
    actor: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowInstance:
    """A running workflow instance with state tracking.

    Usage::

        wf = WorkflowInstance(
            workflow_id="ORD-123",
            current_state=OrderState.CREATED,
        )
        wf.transition(OrderState.PAYMENT_PENDING, actor="checkout_service")
        wf.transition(OrderState.PAYMENT_CONFIRMED, actor="stripe_webhook")
    """

    workflow_id: str
    current_state: OrderState
    history: list[WorkflowTransition] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def can_transition(self, to_state: OrderState) -> bool:
        """Check if a transition is allowed from the current state."""
        allowed = _ORDER_TRANSITIONS.get(self.current_state, [])
        return to_state in allowed

    def transition(
        self,
        to_state: OrderState,
        actor: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowTransition:
        """Execute a state transition.

        Raises ValueError if the transition is not allowed.
        """
        if not self.can_transition(to_state):
            allowed = _ORDER_TRANSITIONS.get(self.current_state, [])
            allowed_names = [s.value for s in allowed]
            raise ValueError(
                f"Cannot transition from {self.current_state.value} to {to_state.value}. "
                f"Allowed: {allowed_names}"
            )

        record = WorkflowTransition(
            from_state=self.current_state.value,
            to_state=to_state.value,
            timestamp=datetime.now(timezone.utc),
            actor=actor,
            metadata=metadata or {},
        )
        self.history.append(record)
        self.current_state = to_state
        return record

    @property
    def is_terminal(self) -> bool:
        """Check if the workflow is in a terminal state."""
        return len(_ORDER_TRANSITIONS.get(self.current_state, [])) == 0

    @property
    def transition_count(self) -> int:
        """Number of transitions that have occurred."""
        return len(self.history)
