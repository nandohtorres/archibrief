# Independent review, 2026-10-21

Baseline preserved at `16438e8`; frozen key SHA-256 is unchanged. New work is
isolated on `mobile-laptop/fix/adversarial-bugs`. Offline Trivy 0.76.0:
81 failed / 154 passed, matching the reported adversarial baseline.

| Bug | Verdict and independently checked evidence | Planned disposition |
|---|---|---|
| B1 | Confirmed: F02 partner_doc loses its ExternalId condition; renderer omits negative elements. | Preserve policy semantics and wildcard principals with focused regressions. |
| B2 | Confirmed: F03 dangerous returns no IMDS findings; account-default early return ignores launch overrides and region. | Apply defaults only to unset settings with matching provider scope. |
| B3 | Confirmed: root tfvars assignments are parsed but discarded; F01 orders is falsely private. | Apply documented automatic variable-file precedence; disclose unselected variable-file uncertainty. |
| B4 | Confirmed: parser collects every directory, not instantiated module calls; F01 dead modules get findings. | Scope proposal sent to user before implementation; filter scanner evidence consistently with evaluation scope. |
| B5 | Confirmed: module blocks are not read; not_observable is neither populated correctly nor surfaced. | Disclose unsupported module coverage in findings and summary; never claim fetched contents. |
| B6 | Confirmed: one-line module source escapes line-anchored regex. | Structural source-expression rewriting; fail closed before scanner on unsupported syntax. |
| B7 | Confirmed: 201-result boundary loses public RDS and lacks truncation metadata. | Bound results, disclose totals, prioritize concern/severity coverage, run deduplicated own-rule fallback for incomplete scans. |
| B8 | Confirmed: eleven backup rules become ten silently. | Explicit total/truncation metadata; preserve decisive bounded evidence where possible, otherwise disclose omission. |
| B9 | Confirmed: region_a/region_b long names display identically. | Deterministic hash suffix for truncated resource and module segments. |
| B10 | Confirmed: HTTPS-only Condition suppresses a publicly readable bucket policy. | Recognize only proven restrictive positive conditions; reject wildcard/negated/unresolved restrictions. |
| B11 | Confirmed: almost_admin and s3_everything_else are missed. | Detect complement grants, without claiming all NotAction policies are full admin. |
| B12 | Confirmed: bounded_worker is described as getting permissions across the whole account. | Retain broad attachment warning but qualify effective permissions by boundary. |
| B13 | Confirmed: orphan_any is called reachable although unattached; routes/listeners are not proved. | Describe permissive configuration, not demonstrated reachability. |
| B14 | Confirmed: false-default ternary count is treated as created. | Narrow static conditional resolution; unresolved expressions stay unknown. |
| B15 | Confirmed: wildcard policy-document principal is rendered into an unrecognized form. | Normalize wildcard principal with B1, preserving restrictive conditions. |
| B16 | Confirmed: malformed-HCL probes return parser content and temporary paths. | Stable sanitized error category, trusted relative identifier and numeric location only; sanitize encoding errors too. |
| B17 | Confirmed: log default retention is displayed as 0, not never expires. | Explicit never-expire wording for omitted and zero retention. |
| B18 | Confirmed: module.edge_lab becomes a phantom resource of type module. | Reconcile concrete identifiers where supported; otherwise disclose module-level attribution. |
| B19 | Confirmed: provider source is rewritten by source-line regex. | Limit structural rewriting to module source attributes, with B6. |
| B20 | Confirmed: omitted named resource finding is put in account_findings. | Distinguish omitted-resource attribution without weakening the frozen key. |

## Probe and adjudication review

- Agree with F02-D-15: generic recommendation text containing 'role' does
  not establish a false attachment claim. Preserve raw output separately.
- Agree with F02-D-05 and F03-D-04/05/06: baseline passes have the wrong
  reason or are vacuous. Recheck their actual behavior after fixes.
- Agree that empty backup-selection/lifecycle summary entries do not
  satisfy meaningful coverage; keep those expectations separate from bugs.
- Additional artifact: F01-D-05 probes `unused_legacy/legacy_db`, but the
  parser's actual name is `modules/unused_legacy/legacy_db`. Add a focused
  exact-name regression; never alter answer_key.json or its hash.
- Backup completeness probe merely checks whether a key contains
  'truncat'; supplement it with exact counts, truthful flags and retained
  rule assertions. Disclosure alone does not satisfy F06-D-02.
- F10-G-61 explicitly requires the old account_findings representation.
  Correcting the representation needs a documented test/probe adjudication
  and stronger resource-attribution assertions, not a weakened expectation.
- Correct B1's suggested condition explanation: positive values under the
  same operator/key generally use OR; separate keys/operators use AND.
- B10's proposed key-name whitelist is insufficient: negated operators,
  IfExists, wildcard principals and world-sized CIDRs are not restrictions.
- Arbitrary non-auto tfvars presence is not proof of CLI selection. Do not
  silently load it or pretend an execution environment was inspected.

Code and security reviewers independently inspected the baseline; they will
also review the full final branch diff. No model, Guardrails, deployed
workflow or chat result is inferred from these deterministic checks.
