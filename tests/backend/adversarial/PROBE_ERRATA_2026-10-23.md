# Post-freeze lexical probe corrections

Version: `probe-errata@2026-10-23`. The answer key, fixtures, raw probe logic and
saved results remain unchanged. This records why two frozen assertions need
supplemental typed configuration contracts after the coverage expansion.

| Check | Frozen mismatch | Supplemental requirement |
|---|---|---|
| F06-D-04 | Matches any `region` or `account` text in the backup-plan summary, including explicit unknown account identity and truthful same-Region configuration | The actual rule-11 copy relationship targets the secondary vault, both configured Regions are `us-east-1`, and accounts remain unknown. A changed destination Region fails. |
| F08-D-04 | Matches the bucket name plus `versioning` anywhere in a finding, including the affirmative statement that versioning is Enabled while noncurrent expiration is absent | The actual versioning observation is Enabled and every matching rule finding is the explicit noncurrent-expiration concern with affirmative versioning evidence. An added missing-versioning finding fails. |

`test_probe_errata.py` proves that the raw frozen probes still fail, the corrected
contracts pass on current fixtures, and the specified counterexamples fail.
`test_adversarial_families.py` accepts the supplemental contract only for these
two known lexical false positives when the raw assertion fails. New runner
exports retain the raw failure, attach the versioned supplemental result and
explanation, and label any corrected adjudicated pass explicitly. Historical
results are not regenerated. This is not a general prose entailment evaluator
or a model-quality score. It does not waive any actual missing-versioning or
cross-Region attribution defect.
