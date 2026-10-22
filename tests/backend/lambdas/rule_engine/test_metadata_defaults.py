import pytest

from backend.lambdas.rule_engine.handler import rule_ec2_imdsv2_required


@pytest.mark.parametrize("resource_type", ["aws_instance", "aws_launch_template"])
@pytest.mark.parametrize(("body", "expected"), [
    ({"metadata_options": [{"http_tokens": "optional"}]}, True),
    ({"provider": "${aws.west}"}, True),
    ({"region": "us-west-2"}, True),
    ({}, False),
    ({"metadata_options": [{"http_tokens": "required"}]}, False),
    ({"metadata_options": [{"http_endpoint": "disabled"}]}, False),
])
def test_metadata_default_applies_only_to_unset_options_in_the_same_scope(resource_type, body, expected):
    parsed = {"resources": {
        "aws_ec2_instance_metadata_defaults": {"east": {"http_tokens": "required"}},
        resource_type: {"worker": body},
    }}
    findings = rule_ec2_imdsv2_required(parsed, "metadata-defaults")
    assert bool(findings) is expected
