from backend.lambdas.rule_engine.hcl_eval import (
    is_created,
    policy_statements,
    resolve,
    truthy,
)

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
