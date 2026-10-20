"""ADR-0030 kill switch for paid entry points outside the review state machine.

The state machine checks the SSM parameter itself (CheckKillSwitch), but
"go deeper" and clarification-resume start paid work through API Lambdas
that never pass that state. Both call this first.

Fails closed: an unset parameter name or an unreadable parameter counts as
"paid work disabled", so a misconfiguration can't silently bypass the stop.
"""

from __future__ import annotations

import os
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def paid_work_allowed(ssm_client: Any | None = None) -> bool:
    name = os.environ.get("KILL_SWITCH_PARAMETER_NAME")
    if not name:
        return False
    client = ssm_client or boto3.client("ssm")
    try:
        value = client.get_parameter(Name=name)["Parameter"]["Value"]
    except (BotoCoreError, ClientError, KeyError, TypeError):
        return False
    # Same semantics as the state machine's KillSwitchGate: "true" = stop.
    return value.strip().lower() != "true"
