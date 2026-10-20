---
title: "ADR 0049: Give the Reasoning Model a Sanitized Resource Summary"
type: decision
tags: [adr, project, work-project, archibrief, security, reasoning]
created: "2026-10-15"
updated: "2026-10-15"
status: accepted
---

# ADR 0049: Give the Reasoning Model a Sanitized Resource Summary

**Status:** Accepted (2026-10-15). Decided by Fernando. Covers master-list
item #15b.

## Context

The reasoning model never sees the submitted Terraform: submitted code is
untrusted, and keeping it out of the prompt is a defense against prompt
injection (ADR-0038). It only saw the rule findings.

So it guessed about anything no rule mentioned. In the first live
end-to-end review with the Scan step (2026-10-15), it wrote an
"assumption" finding that Multi-AZ for the database was "not observable
and is likely absent". The submitted Terraform set `multi_az = true`.

Two fixes were considered:

1. Give the model the facts, in a form that can't carry instructions.
2. Have Validate reject model claims about settings the Terraform answers.

## Decision

Option 1. RuleEngine builds a resource summary and Step Functions passes it
to Reason as `terraform_resources`
(`backend/lambdas/rule_engine/resource_summary.py`).

- **Every resource the Terraform creates**, by type and cleaned name.
  Resources with `count = 0` are left out. The list is capped at 80
  entries and marked when truncated.
- **Settings only from an allowlist per resource type**, for example
  `multi_az`, `storage_encrypted` and `backup_retention_period` for
  `aws_db_instance`.
- **Values** are resolved the same way the rules resolve them (variable
  defaults, locals). Each value is one of:
  - a boolean or a number;
  - a short identifier-like string (letters, digits, `._:-`, at most 32
    characters);
  - `"not set"`: the setting is left at the provider default;
  - `"unknown"`: anything else, including references that can't be
    resolved statically.
- **Never included:** comments, descriptions, tags or policy text.
- **Names** go through the same `display_name()` cleaning as finding text:
  identifier characters only, at most 32 characters.
- **Resource types** must be lowercase snake case, at most 64 characters.
- **The prompt** lists `terraform_resources` with the other untrusted data,
  and tells the model to treat it as the facts. The model must never
  contradict a listed setting. For a setting that isn't listed, it uses
  "not-observable" or recommends checking, rather than guessing.
- Prompt version bumped to `reason_prompt@2026-10-15b`.

Option 2 stays available as a later safety net. It's harder to do well,
because it means matching free-text claims to settings.

## Consequences

- The model reasons from the configuration's real settings. It can no
  longer contradict them without the contradiction being visible.
- The attack surface grows slightly. A submitter now reaches the prompt
  through allowlisted string values as well as resource names. Both are
  capped at 32 identifier characters, the same limit accepted for names in
  ADR-0048 (#14). The threat-model row T14 now covers both.
- **Deploy:**
  - rebuild the rule_engine zip and the AgentCore runtime package;
  - one `terraform apply` (the state machine passes the new field).
- **Proving it live:**
  - re-run the injection trap briefs, which is a paid run;
  - re-run a review like the 2026-10-15 one to confirm the Multi-AZ
    claim is gone.
- The go-deeper path doesn't send the summary yet; it gets an empty one.

## Amendment (2026-10-15, after the live and trap runs)

The first version fixed the Multi-AZ claim, but runs showed three gaps, now closed (`d6887af`):

- **Defaults:** the model guessed provider defaults, sometimes wrongly. Settings with a fixed, documented default now read `"not set (default: X)"`; ones that depend on the account, AMI or subnet stay plain `"not set"` and must not be asserted.
- **Values:** a 19-character `IGNORE_ALL_FINDINGS` engine passed the 32-character identifier check. String values now only come from each setting's real formats (known engines, `db.x.y` instance classes, and so on); anything else is `"unknown"`. Resource names are the only free-form text left, as accepted in T14.
- **Coverage:** the model read settings missing from the summary as missing from the code. The summary now carries a fixed note that only named settings were checked.

Prompt version `reason_prompt@2026-10-15d`. Trap briefs trap09 (injection) and trap10 (contradiction) cover the summary.

## Alternatives considered

- **Raw Terraform to the model:** the most context, but it reopens the
  injection channel ADR-0038 closed. Rejected.
- **Validate rejects contradicting claims (option 2):** it treats the
  symptom, drops findings instead of correcting them, and is fragile on
  free text. Deferred as a possible safety net.
- **More rules for every setting:** the model would still guess about
  anything no rule covers, and a rule only fires on bad settings, never
  confirming good ones.
