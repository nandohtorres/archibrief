from backend.lambdas.rule_engine.handler import run_rules


def test_s3_bucket_without_public_access_block_flagged():
    parsed = {"resources": {"aws_s3_bucket": {"data": {"bucket": "my-bucket"}}}}
    findings = run_rules(parsed, "review-1")
    assert any("public_access_block" in f.finding for f in findings)


def test_s3_bucket_with_public_access_block_not_flagged():
    parsed = {
        "resources": {
            "aws_s3_bucket": {"data": {"bucket": "my-bucket"}},
            "aws_s3_bucket_public_access_block": {
                "data": {"bucket": "${aws_s3_bucket.data.id}"}
            },
        }
    }
    findings = run_rules(parsed, "review-1")
    assert not any("public_access_block" in f.finding for f in findings)


def test_security_group_open_ssh_flagged():
    parsed = {
        "resources": {
            "aws_security_group": {
                "sg": {
                    "ingress": [
                        {"from_port": 22, "to_port": 22, "cidr_blocks": ["0.0.0.0/0"]}
                    ]
                }
            }
        }
    }
    findings = run_rules(parsed, "review-1")
    assert any("0.0.0.0/0" in f.finding and "22" in f.finding for f in findings)


def test_security_group_restricted_cidr_not_flagged():
    parsed = {
        "resources": {
            "aws_security_group": {
                "sg": {
                    "ingress": [
                        {"from_port": 22, "to_port": 22, "cidr_blocks": ["10.0.0.0/8"]}
                    ]
                }
            }
        }
    }
    findings = run_rules(parsed, "review-1")
    assert not any("0.0.0.0/0" in f.finding for f in findings)


def test_rds_unencrypted_flagged():
    parsed = {"resources": {"aws_db_instance": {"db": {}}}}
    findings = run_rules(parsed, "review-1")
    assert any("storage_encrypted" in f.finding for f in findings)


def test_rds_encrypted_not_flagged():
    parsed = {
        "resources": {
            "aws_db_instance": {"db": {"storage_encrypted": True, "multi_az": True}}
        }
    }
    findings = run_rules(parsed, "review-1")
    assert not any("storage_encrypted" in f.finding for f in findings)


def test_cloudtrail_absent_flagged():
    findings = run_rules({"resources": {}}, "review-1")
    assert any("aws_cloudtrail" in f.finding for f in findings)


def test_iam_policy_wildcard_flagged():
    parsed = {
        "resources": {
            "aws_iam_policy": {
                "p": {"policy": '{"Statement": [{"Action": "*", "Resource": "*"}]}'}
            }
        }
    }
    findings = run_rules(parsed, "review-1")
    assert any("wildcard" in f.finding for f in findings)


def test_dynamodb_no_pitr_flagged():
    parsed = {"resources": {"aws_dynamodb_table": {"t": {}}}}
    findings = run_rules(parsed, "review-1")
    assert any("point-in-time recovery" in f.finding for f in findings)


def test_dynamodb_pitr_enabled_as_block_list_not_flagged():
    parsed = {
        "resources": {
            "aws_dynamodb_table": {"t": {"point_in_time_recovery": [{"enabled": True}]}}
        }
    }
    findings = run_rules(parsed, "review-1")
    assert not any("point-in-time recovery" in f.finding for f in findings)


def test_s3_versioning_enabled_via_reference_not_flagged():
    parsed = {
        "resources": {
            "aws_s3_bucket": {"data": {"bucket": "my-bucket"}},
            "aws_s3_bucket_versioning": {
                "data": {
                    "bucket": "${aws_s3_bucket.data.id}",
                    "versioning_configuration": [{"status": "Enabled"}],
                }
            },
        }
    }
    findings = run_rules(parsed, "review-1")
    assert not any("versioning" in f.finding for f in findings)


def test_lambda_secret_env_without_vpc_flagged():
    parsed = {
        "resources": {
            "aws_lambda_function": {
                "fn": {"environment": [{"variables": {"DB_PASSWORD": "x"}}]}
            }
        }
    }
    findings = run_rules(parsed, "review-1")
    assert any("secret-like environment variables" in f.finding for f in findings)


def test_all_findings_are_deterministic_rule_result_type():
    parsed = {"resources": {"aws_s3_bucket": {"data": {"bucket": "b"}}}}
    findings = run_rules(parsed, "review-1")
    assert all(f.type.value == "deterministic-rule-result" for f in findings)
    assert all(f.deterministic_rule_version for f in findings)


def test_handler_loads_parsed_terraform_from_s3_reference(monkeypatch):
    import json

    import backend.lambdas.rule_engine.handler as handler_module

    parsed = {"resources": {"aws_s3_bucket": {"data": {"bucket": "b"}}}}

    class _FakeS3:
        def __init__(self, bucket: str):
            assert bucket == "reports"

        def get_object(self, key: str) -> bytes:
            assert key == "parsed/r1.json"
            return json.dumps(parsed).encode()

    monkeypatch.setattr(handler_module, "S3Client", _FakeS3)
    result = handler_module.handler(
        {
            "review_id": "r1",
            "parsed_s3_key": "parsed/r1.json",
            "report_bucket": "reports",
        },
        None,
    )

    assert any("public_access_block" in f["finding"] for f in result["findings"])


# Regression cases from the October 2026 portfolio review: a missing
# declaration in the submitted code is not proof about the whole account.


def test_s3_encryption_finding_does_not_claim_data_is_unencrypted():
    parsed = {"resources": {"aws_s3_bucket": {"data": {"bucket": "my-bucket"}}}}
    finding = next(
        f
        for f in run_rules(parsed, "review-1")
        if "server-side encryption" in f.finding
    )
    assert not finding.risk_impact.startswith("Data at rest is unencrypted")
    assert "does not mean data is unencrypted" in finding.risk_impact
    # S3 encrypts new objects by default (SSE-S3) since January 2023.
    assert "by default" in finding.risk_impact


def test_cloudtrail_finding_allows_for_a_trail_managed_elsewhere():
    finding = next(
        f
        for f in run_rules({"resources": {}}, "review-1")
        if "aws_cloudtrail" in f.finding
    )
    assert "would not be recorded" not in finding.risk_impact
    assert "managed elsewhere" in finding.risk_impact
    assert "90 days" in finding.risk_impact
    assert finding.recommendation.startswith("Confirm whether")
