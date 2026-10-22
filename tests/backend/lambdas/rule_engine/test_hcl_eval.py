from backend.lambdas.rule_engine.hcl_eval import (
    is_created,
    policy_statements,
    render_policy_document,
    resolve,
    truthy,
)


def test_duplicate_wildcard_principals_have_provider_set_semantics():
    for principals in (
        [{"type": "*", "identifiers": ["*", "*"]}],
        [{"type": "*", "identifiers": ["*"]}] * 2,
    ):
        document = {"statement": [{"principals": principals, "actions": ["s3:GetObject"], "resources": ["*"]}]}
        assert render_policy_document(document, {}, "")["Statement"][0]["Principal"] == "*"


def test_policy_document_preserves_conditions_and_complement_elements():
    document = {"statement": [{
        "not_actions": ["iam:*"], "not_resources": ["arn:aws:s3:::excluded/*"],
        "not_principals": [{"type": "AWS", "identifiers": ["arn:aws:iam::123456789012:root"]}],
        "condition": [
            {"test": "StringEquals", "variable": "sts:ExternalId", "values": ["partner-a"]},
            {"test": "StringEquals", "variable": "sts:ExternalId", "values": ["partner-b"]},
            {"test": "Bool", "variable": "aws:SecureTransport", "values": ["true"]},
        ],
    }]}
    statement = render_policy_document(document, {}, "")["Statement"][0]
    assert statement["NotAction"] == ["iam:*"]
    assert statement["NotResource"] == ["arn:aws:s3:::excluded/*"]
    assert "Action" not in statement and "Resource" not in statement
    assert statement["NotPrincipal"]["AWS"] == ["arn:aws:iam::123456789012:root"]
    assert statement["Condition"] == {
        "StringEquals": {"sts:ExternalId": ["partner-a", "partner-b"]},
        "Bool": {"aws:SecureTransport": ["true"]},
    }


def test_policy_document_normalizes_wildcard_principal_without_losing_conditions():
    document = {"statement": [{
        "actions": ["s3:GetObject"], "resources": ["*"],
        "principals": [{"type": "*", "identifiers": ["*"]}],
        "condition": [{"test": "StringEquals", "variable": "aws:SourceVpce", "values": ["vpce-123"]}],
    }]}
    statement = render_policy_document(document, {}, "")["Statement"][0]
    assert statement["Principal"] == "*"
    assert statement["Condition"]["StringEquals"]["aws:SourceVpce"] == ["vpce-123"]

ADMIN = [{"Effect": "Allow", "Action": "*", "Resource": "*"}]


def test_jsonencode_policy_is_decoded():
    value = '${jsonencode({Version = "2012-10-17", Statement = [{Effect = "Allow", Action = "*", Resource = "*"}]})}'
    assert policy_statements(value, {}) == ADMIN


def test_heredoc_policy_is_decoded():
    value = '<<POLICY\n{"Statement": [{"Effect": "Allow", "Action": "*", "Resource": "*"}]}\nPOLICY'
    assert policy_statements(value, {}) == ADMIN


def test_policy_document_data_source_is_rendered():
    parsed = {
        "data": {
            "aws_iam_policy_document": {
                "everything": {"statement": [{"actions": ["*"], "resources": ["*"]}]}
            }
        }
    }
    statements = policy_statements(
        "${data.aws_iam_policy_document.everything.json}", parsed
    )
    assert statements == [{"Effect": "Allow", "Action": ["*"], "Resource": ["*"]}]


def test_variable_default_and_local_are_followed():
    parsed = {
        "variables": {"enc": {"default": False}},
        "locals": {"bucket": "${aws_s3_bucket.data.id}"},
    }
    assert resolve("${var.enc}", parsed) is False
    assert resolve("${local.bucket}", parsed) == "${aws_s3_bucket.data.id}"


def test_lookups_are_module_scoped():
    parsed = {"variables": {"enc": {"default": True}, "mod/enc": {"default": False}}}
    assert truthy("${var.enc}", parsed, "") is True
    assert truthy("${var.enc}", parsed, "mod") is False


def test_unknown_expressions_stay_unknown():
    assert resolve("${aws_kms_key.main.arn}", {}) == "${aws_kms_key.main.arn}"
    assert truthy("${var.missing}", {}) is None
    assert policy_statements("${var.missing}", {}) is None


def test_reference_cycles_terminate():
    parsed = {"locals": {"a": "${local.b}", "b": "${local.a}"}}
    assert isinstance(resolve("${local.a}", parsed), str)


def test_count_zero_and_empty_for_each_are_not_created():
    parsed = {"variables": {"enabled": {"default": 0}}}
    assert is_created({"count": 0}, parsed) is False
    assert is_created({"count": "${var.enabled}"}, parsed) is False
    assert is_created({"for_each": {}}, parsed) is False
    assert is_created({"count": 2}, parsed) is True
    assert is_created({"count": "${var.unknown}"}, parsed) is True


def test_conditional_counts_resolve_only_known_boolean_conditions():
    parsed = {"variables": {"enabled": {"default": False}}}
    assert resolve("${var.enabled ? 1 : 0}", parsed) == 0
    assert is_created({"count": "${var.enabled ? 1 : 0}"}, parsed) is False
    assert resolve("${true ? 2 : 0}", parsed) == 2
    assert resolve("${var.missing ? 1 : 0}", parsed) == "${var.missing ? 1 : 0}"


def test_unknown_creation_is_qualified_in_rule_findings():
    from backend.lambdas.rule_engine.handler import run_rules

    parsed = {"resources": {"aws_db_instance": {"maybe": {
        "count": "${var.unknown ? 1 : 0}", "publicly_accessible": True
    }}}}
    findings = [f for f in run_rules(parsed, "unknown-count") if "'maybe'" in f.finding]
    assert findings
    assert all("if created" in f.finding.lower() for f in findings)
