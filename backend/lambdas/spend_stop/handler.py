"""Trips the kill switch when the monthly AWS budget's stop alert fires.

Subscribed only to the spend-stop SNS topic, which receives a single
budget notification (actual spend past the stop threshold). Any delivery
on that topic means stop: the message body is not trusted or parsed. The
switch stays on until the owner turns it off; nothing here turns it back on.
"""

from __future__ import annotations

import json
import os

import boto3


def handler(event: dict, _context: object) -> dict:
    name = os.environ["KILL_SWITCH_PARAMETER_NAME"]
    boto3.client("ssm").put_parameter(Name=name, Value="true", Type="String", Overwrite=True)
    print(json.dumps({"event": "kill_switch_tripped", "source": "monthly_budget"}))
    return {"kill_switch": "true"}
