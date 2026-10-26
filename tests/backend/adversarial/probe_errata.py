"""Typed corrections for two lexical probes invalidated by richer output.

The frozen probe still runs and its raw verdict remains unchanged. These
checks cover the specific configuration contracts, not general prose semantics.
"""

VERSION = "probe-errata@2026-10-23"
CHECKS = {"F06-D-04", "F08-D-04"}


def _bundle(run, kind, name):
    return next(
        (
            entry.get("observations", {})
            for entry in run.summary.get("resources", [])
            if entry["type"] == kind and entry["name"] == name
        ),
        {},
    )


def _fact(bundle, setting):
    return next(
        (fact for fact in bundle.get("facts", []) if fact["setting"] == setting), {}
    )


def corrected_probe(check_id, run):
    if check_id == "F06-D-04":
        plan = _bundle(run, "aws_backup_plan", "nightly")
        destination = _bundle(run, "aws_backup_vault", "secondary")
        regions = [_fact(bundle, "resource.region") for bundle in (plan, destination)]
        same_region = (
            all(fact.get("state") == "known" for fact in regions)
            and regions[0].get("value") == regions[1].get("value") == "us-east-1"
        )
        account_unknown = all(
            _fact(bundle, "provider.account").get("state") == "unknown"
            for bundle in (plan, destination)
        )
        linked = any(
            relation.get("target") == "aws_backup_vault.secondary"
            and relation.get("state") == "known"
            and relation.get("setting") == "rule[10].copy[0].destination"
            for relation in plan.get("relations", [])
        )
        return (
            same_region and account_unknown and linked,
            "Inspect explicit copy relationship, equal configured Regions and unknown account identities; word occurrence is not a cross-Region claim.",
        )
    if check_id == "F08-D-04":
        versioning = _bundle(run, "aws_s3_bucket_versioning", "uploads")
        enabled = _fact(versioning, "versioning_configuration.status")
        matched = [
            finding
            for finding in run.findings
            if "'uploads'"
            in " ".join(
                str(finding.get(key) or "")
                for key in ("finding", "evidence", "risk_impact", "recommendation")
            ).lower()
            and "versioning"
            in " ".join(
                str(finding.get(key) or "")
                for key in ("finding", "evidence", "risk_impact", "recommendation")
            ).lower()
        ]
        correct = (
            enabled.get("state") == "known"
            and enabled.get("value") == "Enabled"
            and bool(matched)
            and all(
                finding.get("concern") == "versioned_retention_gap"
                and "bucket versioning is Enabled" in finding.get("evidence", "")
                for finding in matched
            )
        )
        return (
            correct,
            "The bucket has Enabled versioning; the identified rule concerns noncurrent expiry and explicitly preserves that setting.",
        )
    return False, "No supplemental probe correction is defined."
