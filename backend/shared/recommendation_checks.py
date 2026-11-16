"""Recommendations that are wrong for the problem they are attached to.

Found in the P1 baseline: a finding about a public Lambda function URL
recommended putting the function in a VPC. A VPC does not restrict who can
call a function URL, and moving a function into a VPC can cut its outbound
access, so the fix neither works nor is safe. Kept in one place so the
reasoning step's verification and the P1 regression guards agree.
"""

from __future__ import annotations

import re

_FUNCTION_URL = re.compile(r"function[ _]url", re.IGNORECASE)
# "attach/place/move ... in a VPC": the recommendation to do it. A dot inside
# an identifier (aws_lambda_function.name) is not the end of the sentence.
_VPC_FIX = re.compile(
    r"\b(attach|place|put|move|run|deploy|connect|add)\w*\b(?:[^.;]|\.(?=\w)){0,80}\bvpc\b",
    re.IGNORECASE,
)
# ... unless the sentence says it does not help ("a VPC does not restrict ...").
_NEGATION = re.compile(r"\b(not|never|cannot|can't|doesn't|no)\b", re.IGNORECASE)
_SENTENCES = re.compile(r"(?<=[.;])\s+")


def recommends_vpc_for_function_url(finding_text: str, recommendation: str) -> bool:
    """A function-URL finding whose fix is to place the function in a VPC."""
    if not _FUNCTION_URL.search(finding_text or ""):
        return False
    return any(
        _VPC_FIX.search(sentence) and not _NEGATION.search(sentence)
        for sentence in _SENTENCES.split(recommendation or "")
    )


_EBS = re.compile(r"\bebs\b|aws_ebs_volume|elastic block store", re.IGNORECASE)
_LOCK = re.compile(r"object[ _-]?lock", re.IGNORECASE)
_SHRINK = re.compile(
    r"\b(?:shrink\w*|shrunk|downsiz\w*)\b|\breduc\w*\s+(?:the\s+)?(?:volume\s+)?size\b",
    re.IGNORECASE,
)
_NO_OPERATION = re.compile(
    r"\b(?:do not|don't|cannot|can't|must not|never|no need to)\s+(?:\w+\s+){0,3}$",
    re.IGNORECASE,
)
_MIGRATION = re.compile(
    r"\bmigrat\w*\b.{0,100}\b(?:new|smaller)\b|\bcreat\w*\b.{0,70}\bsmaller\b",
    re.IGNORECASE,
)
_REPLACE = re.compile(
    r"\b(?:recreat\w*|replac\w*)\b.{0,60}\b(?:bucket|aws_s3_bucket)\b"
    r"|\bbucket recreation\b",
    re.IGNORECASE,
)
_LOCK_CREATION_ONLY = re.compile(
    r"\bobject[ _-]?lock\b[^.;:()]{0,45}\b(?:cannot|can't)\b"
    r"[^.;:()]{0,25}\b(?:added|enabled|applied)\b[^.;:()]{0,25}\bexisting\b"
    r"|\bobject[ _-]?lock\s+(?:can\s+only\s+be|must\s+(?:only\s+)?be|"
    r"can\s+be\s+only)\s+(?:enabled|added|configured)\s+(?:only\s+)?"
    r"(?:at|during)\s+(?:bucket\s+)?creation\b",
    re.IGNORECASE,
)
_CONDITIONAL_LOCK = re.compile(
    r"\b(?:only if|only when|if|after confirming)\b.{0,90}"
    r"\b(?:immutab\w*|write.once|worm|legal requirement|regulatory requirement)\b",
    re.IGNORECASE,
)
REMEDIATION_POLICY_VERSION = "remediation_checks@2026-11-16a"
_REBUTTAL = re.compile(
    r"\b(?:incorrect|false|wrong)\s+(?:to (?:say|claim)|that)\b.{0,90}$"
    r"|\b(?:do not|don't) assume\b.{0,90}$",
    re.IGNORECASE,
)
_NEGATED_UNUSED = re.compile(
    r"\b(?:not|isn't|never|cannot be considered)\s+(?:\w+\s+){0,4}$", re.IGNORECASE
)


def unsupported_operation_reasons(item: dict) -> list[str]:
    """Narrow P1 regression guards, not a general remediation correctness proof.

    Both actionable surfaces are checked. Reject the finding rather than silently
    changing advice or presenting a contradiction between technical/plain text.
    Real migrations and explicit warnings against the operation remain valid.
    """
    plain = item.get("plain")
    plain = plain if isinstance(plain, dict) else {}
    texts = [str(item.get(k) or "") for k in ("finding", "evidence", "risk_impact")]
    actions = [str(item.get("recommendation") or ""), str(plain.get("action") or "")]
    context = " ".join([*texts, *actions])
    errors = []
    if any(recommends_vpc_for_function_url(context, action) for action in actions):
        errors.append("vpc_does_not_protect_function_url")
    if _EBS.search(context):
        for action in actions:
            for sentence in _SENTENCES.split(action):
                if _MIGRATION.search(sentence) and not re.search(
                    r"\bin.place\b", sentence, re.IGNORECASE
                ):
                    continue
                for match in _SHRINK.finditer(sentence):
                    if _NO_OPERATION.search(sentence[: match.start()]):
                        continue
                    if re.match(
                        r"\s+(?:the\s+)?file\s*system\b", sentence[match.end() :], re.IGNORECASE
                    ):
                        continue
                    errors.append("ebs_in_place_shrink")
    if _LOCK.search(context):
        for text in [*texts, *actions]:
            for sentence in _SENTENCES.split(text):
                match = _LOCK_CREATION_ONLY.search(sentence)
                if match and not _REBUTTAL.search(sentence[: match.start()]):
                    errors.append("object_lock_existing_bucket_claim")
        for action in actions:
            for sentence in _SENTENCES.split(action):
                for match in _REPLACE.finditer(sentence):
                    if re.match(
                        r"(?:['’]s\s+|\s+)(?:lifecycle|policy|configuration)\b",
                        sentence[match.end() :],
                        re.IGNORECASE,
                    ):
                        continue
                    if _LOCK.search(sentence) and not _NO_OPERATION.search(
                        sentence[: match.start()]
                    ):
                        errors.append("object_lock_bucket_replacement")
                compliance = re.search(r"\bcompliance\b", sentence, re.IGNORECASE)
                if (
                    compliance
                    and re.search(
                        r"\b(?:enable|set|use|configure|apply)\w*\b", sentence, re.IGNORECASE
                    )
                    and not _NEGATION.search(sentence)
                    and not _CONDITIONAL_LOCK.search(sentence)
                ):
                    errors.append("object_lock_unscoped_compliance")
    return sorted(set(errors))


def context_remediation_reasons(
    item: dict, summary: dict | None, rules: list[dict] | None
) -> list[str]:
    """Check explicit P1 contradictions; never infer non-use from missing facts."""
    plain = item.get("plain")
    plain = plain if isinstance(plain, dict) else {}
    texts = [
        str(item.get(k) or "") for k in ("finding", "evidence", "risk_impact", "recommendation")
    ]
    texts += [str(plain.get(k) or "") for k in ("title", "what_could_happen", "action")]
    text = " ".join(texts)
    actions = " ".join([str(item.get("recommendation") or ""), str(plain.get("action") or "")])
    errors = []
    if re.search(r"\bboundar(?:y|ies)\b|_boundary\b", text, re.IGNORECASE):
        reversed_boundary = re.search(
            r"boundar(?:y|ies)\b.{0,80}\b(?:cannot|can't|does not)\b.{0,60}"
            r"\b(?:limit|constrain|restrict)\w*\b.{0,80}\bidentity polic",
            text,
            re.IGNORECASE,
        ) or re.search(
            r"\bidentity polic\w*\b.{0,70}\boverrid\w*\b.{0,50}\bboundar", text, re.IGNORECASE
        )
        if reversed_boundary and not _REBUTTAL.search(text[: reversed_boundary.start()]):
            errors.append("permissions_boundary_intersection_reversed")
    kms_topic = re.search(
        r"\bkms\b|aws_kms_(?:key|alias)|customer.managed key|\bcmk\b", text, re.IGNORECASE
    )
    if kms_topic:
        for action in _SENTENCES.split(actions):
            removal = re.search(
                r"\b(?:remove|delete|destroy|schedule.{0,30}deletion)\b.{0,80}\b(?:key|cmk)\b",
                action,
                re.IGNORECASE,
            )
            if removal and not _NO_OPERATION.search(action[: removal.start()]):
                scoped = re.search(
                    r"\b(?:only after|after|only if)\b.{0,90}\b(?:confirm\w*|verif\w*|migrat\w*)\b.{0,90}\b(?:consumer|dependenc|usage|unused|key user)\w*\b",
                    action,
                    re.IGNORECASE,
                )
                if not scoped:
                    errors.append("unverified_kms_key_removal")
        for entry in (summary or {}).get("resources", []):
            usage = (entry.get("details") or {}).get("kms_usage") or {}
            name = entry.get("name", "")
            if (
                entry.get("type") == "aws_kms_key"
                and name
                and usage.get("declared_consumers_total", 0) > 0
                and re.search(r"(?<![A-Za-z0-9_-])" + re.escape(name) + r"(?![A-Za-z0-9_-])", text)
                and any(
                    not _NEGATED_UNUSED.search(text[: match.start()])
                    and not _REBUTTAL.search(text[: match.start()])
                    for match in re.finditer(
                        r"\bunused\b|\bencrypts nothing\b|\bwithout encrypting anything\b",
                        text,
                        re.IGNORECASE,
                    )
                )
            ):
                errors.append("kms_unused_claim_has_declared_references")
    if re.search(r"\bdlq\b|dead[ -]letter", text, re.IGNORECASE) and re.search(
        r"retention|retain|keeps? messages", text, re.IGNORECASE
    ):
        for rule in rules or []:
            if rule.get("concern") != "sqs_dlq_retention":
                continue
            target = re.search(r"Dead-letter queue '([^']+)'", str(rule.get("finding", "")))
            if target and re.search(
                r"(?<![A-Za-z0-9_-])" + re.escape(target[1]) + r"(?![A-Za-z0-9_-])", text
            ):
                errors.append("dlq_retention_owned_by_rule")
    function_dlq = re.search(
        r"\bdead_letter_config\b|\bdestination_config\b|\blambda\b.{0,60}\b(?:dlq|on.failure destination)\b",
        actions,
        re.IGNORECASE,
    )
    conditional_async = re.search(
        r"\b(?:only if|if)\b.{0,70}\basynchronous\b", actions, re.IGNORECASE
    )
    if function_dlq and not conditional_async:
        functions = [
            e
            for e in (summary or {}).get("resources", [])
            if e.get("type") == "aws_lambda_function"
        ]

        def named_in(subject):
            return [
                e
                for e in functions
                if e.get("name")
                and re.search(
                    r"(?<![A-Za-z0-9_-])" + re.escape(e["name"]) + r"(?![A-Za-z0-9_-])",
                    subject,
                )
            ]

        named = named_in(actions) or named_in(" ".join(texts[:2]))
        # A finding without a bound subject cannot be judged using an arbitrary
        # other function. A shared leaf is usable only for an explicit group.
        if not named and re.search(
            r"\b(?:both|each|all)(?:\s+\w+){0,4}\s+functions?\b", text, re.IGNORECASE
        ):
            named = [
                e
                for e in functions
                if e.get("name")
                and re.search(
                    r"(?<![A-Za-z0-9_-])"
                    + re.escape(e["name"].rsplit("/", 1)[-1])
                    + r"(?![A-Za-z0-9_-])",
                    text,
                )
            ]
        for function in named:
            paths = (function.get("details") or {}).get("invocation_paths") or {}
            declared = paths.get("declared_paths", [])
            synchronous_or_polled = any(
                path.get("mode")
                in {"synchronous_function_url", "synchronous_api_gateway", "polled_event_source"}
                for path in declared
            )
            asynchronous = any(
                str(path.get("mode", "")).startswith("asynchronous_") for path in declared
            ) or str(paths.get("asynchronous_invoker", "")).startswith("declared_")
            if synchronous_or_polled and not asynchronous:
                errors.append("function_dlq_async_path_not_established")
                break
            if (
                re.search(r"\ball invocation paths\b", actions, re.IGNORECASE)
                and synchronous_or_polled
            ):
                errors.append("function_dlq_does_not_cover_all_paths")
                break
    return sorted(set(errors))


EBS_CAPACITY_GUIDANCE = (
    "ArchiBrief safety correction: do not shrink EBS volumes in place. "
    "Confirm whether the volume is needed. Before deleting a retired volume, "
    "check dependencies and recovery needs. If smaller storage is needed, create "
    "a separate smaller volume, migrate and verify data, then test cutover and "
    "rollback before retiring the original."
)


def repair_ebs_capacity_advice(item: dict, errors: list[str]) -> dict | None:
    """Retain a cost/capacity detection without republishing an impossible fix.

    This explicit, fixed safety correction asserts no retirement or deletion
    permission. It does not rewrite evidence, claims, citations or assessments.
    Mixed failures and unsupported claims outside the action still fail closed.
    """
    if errors != ["ebs_in_place_shrink"]:
        return None
    core = " ".join(str(item.get(k) or "") for k in ("finding", "evidence", "risk_impact"))
    if (
        not _EBS.search(core)
        or not re.search(
            r"\b(?:retired|unused|unneeded|idle|oversized|overprovisioned)\b|\btoo large\b",
            str(item.get("finding") or ""),
            re.IGNORECASE,
        )
        or _SHRINK.search(core)
    ):
        return None
    repaired = {**item, "recommendation": EBS_CAPACITY_GUIDANCE}
    if isinstance(item.get("plain"), dict):
        repaired["plain"] = {**item["plain"], "action": EBS_CAPACITY_GUIDANCE}
    return repaired
