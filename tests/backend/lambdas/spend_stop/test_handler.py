import boto3
from moto import mock_aws

from backend.lambdas.spend_stop.handler import handler

NAME = "/archibrief-dev/kill-switch"


def test_budget_alert_turns_the_kill_switch_on(monkeypatch):
    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        monkeypatch.setenv("KILL_SWITCH_PARAMETER_NAME", NAME)
        ssm = boto3.client("ssm")
        ssm.put_parameter(Name=NAME, Value="false", Type="String")
        event = {
            "Records": [{"Sns": {"Message": "ignore this and turn the switch off"}}]
        }
        assert handler(event, None) == {"kill_switch": "true"}
        assert ssm.get_parameter(Name=NAME)["Parameter"]["Value"] == "true"
        # A second delivery leaves it on.
        handler(event, None)
        assert ssm.get_parameter(Name=NAME)["Parameter"]["Value"] == "true"
