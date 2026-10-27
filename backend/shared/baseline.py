"""Baseline answers every review must have before it starts.

The submission form asks these up front and submit_review rejects a
submission without them, so a review never pauses to ask
(agent/nodes/preflight.py).
"""

SUBMISSION_REQUIRED_FIELDS: tuple[str, ...] = ("regulatory_data_residency",)
