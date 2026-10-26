# A measured static remediation example

This owned, minimal example demonstrates one deterministic finding disappearing
after a targeted change. It is not a deployed workload or model-quality result.
No Terraform or AWS API is executed. Do not deploy these illustrative bucket
names as a production configuration.

Before: a versioned bucket expires current objects after seven days but declares
no noncurrent-version expiration. After: the same rule adds one-day noncurrent
expiration. The checked working-copy policy intentionally permits old versions
to expire; deletion remains asynchronous and backups, holds and other copies
need separate review. This does not prove exact deletion after eight days.

Run from the repository root with the existing backend dependencies:

```text
python scripts/verify_retention_example.py
```

The script compares real custom-rule output, excluding random finding IDs.
It succeeds only if exactly `versioned_retention_gap` disappears, no new finding
is added and every other finding is preserved. The saved result records the
actual run, file hashes and limits. Trivy and paid reasoning were not evaluated.

A useful future contextual comparison uses the same `after.tf` with two briefs:
nonessential working uploads whose old versions may expire, versus records with
a workload requirement to retain every version for seven years. The deterministic
settings stay identical; a model should assess their suitability against each
requirement. That paired model comparison is **not run or scored** here and needs
separate authorized evaluation. No result is invented for it.
