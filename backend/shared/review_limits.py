"""Server-owned declaration policy for P2's small-workload pilot.

This pure check is one prerequisite for paid admission. It does not authorize
dispatch: callers must also verify the stored operation and request budget.
"""

from backend.shared.review_scope import validate_scope

MAX_REVIEW_DECLARATIONS = 50
SCOPE_POLICY_VERSION = "small-workload-pilot@2026-11-11"


def public_scope_failure(value: object) -> dict | None:
    """Only bounded counts leave the rejection path; never expose parser text."""
    if not isinstance(value, dict):
        return None
    count = value.get("known_y")
    complete = value.get("count_complete")
    if type(count) is not int or not 50 < count <= 1000 or type(complete) is not bool:
        return None
    return {"known_y": count, "count_complete": complete}


def scope_rejection_code(scope: object) -> str | None:
    """Return an eligibility failure, or None for a valid known count <=50.

    Accept incomplete inventories and module gaps as labeled partial reviews.
    The count includes unsupported types and zero-copy declarations; never
    substitute the retained summary or created instance count for this total.
    """
    if validate_scope(scope):
        return "scope_manifest_required"
    if scope["state"] != "recorded":
        return "scope_manifest_required"
    if scope["known_y"] > MAX_REVIEW_DECLARATIONS:
        return "resource_limit_exceeded"
    return None
