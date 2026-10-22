import json

import pytest

from backend.lambdas.rule_engine.handler import run_rules


@pytest.mark.parametrize(("condition", "public"), [
    ({"Bool": {"aws:SecureTransport": "true"}}, True),
    ({"StringNotEquals": {"aws:SourceVpce": "vpce-123"}}, True),
    ({"StringEqualsIfExists": {"aws:SourceVpce": "vpce-123"}}, True),
    ({"StringLike": {"aws:PrincipalOrgID": "*"}}, True),
    ({"IpAddress": {"aws:SourceIp": "0.0.0.0/0"}}, True),
    ({"IpAddress": {"aws:SourceIp": ["0.0.0.0/1", "128.0.0.0/1"]}}, True),
    ({"Null": {"aws:SourceVpce": "false"}}, True),
    ({"StringEquals": {"aws:SourceVpce": "${var.endpoint}"}}, True),
    ({"StringEquals": {"aws:SourceVpce": "vpce-123"}}, False),
    ({"IpAddress": {"aws:SourceIp": "192.0.2.0/24"}}, False),
])
def test_public_policy_requires_a_proven_restrictive_condition(condition, public):
    policy = {"Statement": [{"Effect": "Allow", "Principal": "*", "Action": "s3:GetObject", "Resource": "*", "Condition": condition}]}
    parsed = {"resources": {"aws_s3_bucket_policy": {"documents": {"policy": json.dumps(policy)}}}}
    findings = run_rules(parsed, "policy-semantics")
    assert any(f.concern == "s3_public_policy" for f in findings) is public


@pytest.mark.parametrize("statement", [
    {"NotAction": ["iam:*", "organizations:*"], "Resource": "*"},
    {"Action": "s3:*", "NotResource": "arn:aws:s3:::excluded/*"},
])
def test_allow_complement_grants_are_reported_without_claiming_full_admin(statement):
    parsed = {"resources": {"aws_iam_policy": {"complement": {"policy": json.dumps({"Statement": [{"Effect": "Allow", **statement}]})}}}}
    findings = [f for f in run_rules(parsed, "complements") if f.concern == "iam_wildcard"]
    assert findings
    assert all("full admin" not in f.finding for f in findings)
    if "NotResource" in statement:
        assert all("on all resources" not in f.finding for f in findings)
        assert all('on Resource "*"' not in f.evidence for f in findings)
        assert all("NotResource" in f.evidence for f in findings)


def test_compute_role_boundary_qualifies_effective_permissions():
    role = {
        "assume_role_policy": json.dumps({"Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]}),
        "managed_policy_arns": ["arn:aws:iam::aws:policy/AdministratorAccess"],
        "permissions_boundary": "${aws_iam_policy.boundary.arn}",
    }
    findings = [f for f in run_rules({"resources": {"aws_iam_role": {"bounded": role}}}, "boundary") if f.concern == "iam_compute_broad_managed"]
    assert len(findings) == 1
    assert "boundary" in findings[0].risk_impact.lower()
    assert "across the whole account" not in findings[0].risk_impact


def test_open_group_does_not_establish_network_reachability():
    parsed = {"resources": {"aws_security_group": {"orphan": {"ingress": [{
        "from_port": 5432, "to_port": 5432, "cidr_blocks": ["0.0.0.0/0"]
    }]}}}}
    (finding,) = [f for f in run_rules(parsed, "open-rule") if f.concern == "sg_open_ingress"]
    assert "reachable from the entire internet" not in finding.risk_impact
    assert "if attached" in finding.risk_impact
