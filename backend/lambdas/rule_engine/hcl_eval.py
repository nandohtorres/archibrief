"""Compatibility exports for the shared bounded static HCL resolver."""

from backend.shared.hcl_eval import (  # noqa: F401
    is_created,
    policy_statements,
    render_policy_document,
    resolve,
    truthy,
)
