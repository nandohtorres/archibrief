import uuid

from backend.lambdas.validate.handler import validate_findings


def _valid_raw_finding(**overrides):
    raw = {
        "finding_id": str(uuid.uuid4()),
        "review_id": "review-1",
        "category": "iam",
        "type": "deterministic-rule-result",
        "finding": "text",
        "evidence": "evidence",
        "citation": None,
        "confidence": 0.9,
        "confidence_inputs": {
            "evidence_directness": 1.0,
            "source_agreement": 1.0,
            "rule_determinism": 1.0,
        },
        "risk_impact": "impact",
        "recommendation": "fix it",
        "framework_mapping": ["AWS Well-Architected: Security Pillar"],
        "depth_level": "lightweight",
    }
    raw.update(overrides)
    return raw


def test_valid_finding_passes():
    valid, rejected = validate_findings([_valid_raw_finding()])
    assert len(valid) == 1
    assert rejected == []


def test_finding_missing_required_field_rejected():
    raw = _valid_raw_finding()
    del raw["recommendation"]
    valid, rejected = validate_findings([raw])
    assert valid == []
    assert len(rejected) == 1


def test_finding_confidence_out_of_range_rejected():
    raw = _valid_raw_finding(confidence=2.0)
    valid, rejected = validate_findings([raw])
    assert valid == []
    assert len(rejected) == 1


def test_mixed_batch_partitions_correctly():
    good = _valid_raw_finding()
    bad = _valid_raw_finding()
    del bad["citation"]
    bad["type"] = "fact"
    valid, rejected = validate_findings([good, bad])
    assert len(valid) == 1
    assert len(rejected) == 1
