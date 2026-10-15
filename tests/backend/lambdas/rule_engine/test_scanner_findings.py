from backend.lambdas.rule_engine.handler import run_rules
from backend.shared.terraform_scope import display_name

PARSED = {
    "resources": {
        "aws_s3_bucket": {"exports": {"bucket": "acme-exports"}},
        "aws_s3_bucket_public_access_block": {
            "exports_block": {
                "bucket": "${aws_s3_bucket.exports.id}",
                "block_public_acls": False,
            }
        },
    }
}


def _result(check_id: str, resource_type: str, key: str, line: int) -> dict:
    return {
        "check_id": check_id,
        "resource_type": resource_type,
        "resource_key": key,
        "file": "main.tf",
        "start_line": line,
        "end_line": line,
    }


def _scanner(*results: dict) -> dict:
    return {
        "status": "ok",
        "tool": "trivy",
        "version": "0.76.0",
        "results": list(results),
    }


def test_one_finding_per_concern_and_resource_attributed_to_the_bucket():
    scanner = _scanner(
        _result("AWS-0086", "aws_s3_bucket_public_access_block", "exports_block", 8),
        _result("AWS-0087", "aws_s3_bucket_public_access_block", "exports_block", 9),
        _result("AWS-0093", "aws_s3_bucket_public_access_block", "exports_block", 11),
    )

    findings = [
        f for f in run_rules(PARSED, "r1", scanner=scanner) if "Trivy" in f.evidence
    ]

    assert len(findings) == 1
    finding = findings[0]
    assert (
        finding.finding == "Public access to S3 bucket 'exports' is not fully blocked"
    )
    assert "AWS-0086, AWS-0087, AWS-0093" in finding.evidence
    assert "main.tf lines 8-11" in finding.evidence
    assert "SEC08-BP04" in finding.framework_mapping
    assert finding.deterministic_rule_version.endswith("+trivy@0.76.0")


def test_trivy_owned_concerns_replace_archibrief_rules_when_trivy_ran():
    without = run_rules(PARSED, "r1", scanner=None)
    with_trivy = run_rules(PARSED, "r1", scanner=_scanner())

    assert any("public access" in f.finding.lower() for f in without)
    # Trivy reported nothing for public access, and its concern is not
    # double-reported by ArchiBrief's own rule.
    assert not any("public access" in f.finding.lower() for f in with_trivy)


def test_untrusted_check_ids_are_ignored():
    scanner = _scanner(_result("AWS-0132", "aws_s3_bucket", "exports", 1))
    assert not any(
        "Trivy" in f.evidence for f in run_rules(PARSED, "r1", scanner=scanner)
    )


def test_unavailable_scanner_falls_back_and_says_so():
    findings = run_rules(
        PARSED, "r1", scanner={"status": "unavailable", "reason": "timeout"}
    )

    assert any("public access" in f.finding.lower() for f in findings)
    notes = [f for f in findings if f.type.value == "not-observable"]
    assert len(notes) == 1
    assert "Trivy scanner didn't run" in notes[0].finding


def test_scanner_resource_names_are_sanitized():
    scanner = _scanner(_result("AWS-0090", "aws_s3_bucket", "mod/" + "X" * 80, 1))
    finding = next(
        f for f in run_rules({}, "r1", scanner=scanner) if "Trivy" in f.evidence
    )
    assert display_name("mod/" + "X" * 80) in finding.finding
    assert "X" * 40 not in finding.finding


def test_open_database_port_on_standalone_rule_is_archibriefs_even_with_trivy():
    parsed = {
        "resources": {
            "aws_vpc_security_group_ingress_rule": {
                "pg": {
                    "cidr_ipv4": "0.0.0.0/0",
                    "from_port": 5432,
                    "to_port": 5432,
                    "ip_protocol": "tcp",
                }
            }
        }
    }
    findings = run_rules(parsed, "r1", scanner=_scanner())
    assert any("'pg'" in f.finding and "5432" in f.finding for f in findings)
