# Claims that could not be verified

The report keeps rejected claims in a separate, initially collapsed **Unable to verify** section. It explains why each claim failed a check and asks the reader to check it before acting. A visible badge and theme-aware colour distinguish these claims from the counted findings. If initial AI analysis fails or times out, the same section explains that only finished checks are available.

## Separate records, without recommendations

Reason collects citation, format and remediation failures under the optional `unverified_findings` key. Validate adds schema failures. The evidence ledger and report retain this bounded list separately from `findings`; it has no severity assessment, brief card, chat alias or go-deeper action. The existing finding counts and quality counters keep their meaning. Older reports without this field still load; rejection counts without saved text are disclosed.

Each record keeps a bounded claim, submitted evidence, resource label, category/concern when usable, a fixed reason code and a plain explanation. All rejected recommendations are withheld, including plain actions, alternatives and risk prose. Citations are omitted from this separate representation so a failed reference cannot appear endorsed. No raw extra fields are copied into the public record. The original input object is not rewritten.

Limits: at most 24 records in a combined report; claim 1,200 characters, evidence 1,600 and resource 160. Display and both downloads apply the same field allowlist and no-price policy. Deep-review result markers keep their own rejected claims; the current report merges only authorized, unexpired markers into this list. It never adds those claims to the counted findings.

## Chat

When reference checking leaves a generated paragraph without a valid citation, the normal answer excludes it and a bounded, cleaned **Unsupported** note retains the statement. Invalid citations are not displayed as references. These notes are excluded from future chat history and grounding sources; an answer with no supported paragraphs still gets the fixed not-determinable answer. Canary/refusal protections still apply. New, cached and suggested answers pass through the same public serialization and no-price policy, including downloads.

This is disclosure, not an independent judgment that every rejected claim is false or every retained paragraph is correct. Evaluation should distinguish a counted catch from a claim caught only in this separate list. No new accuracy rate follows from adding the section.

## Additional verification

This change is built on the default-off verification candidate. Its request protocol, verdicts, failure policy and budget are unchanged. This section's separate record format can receive verifier dispositions in a future coordinated change; a failed verification call still keeps the original findings marked unchecked under the existing policy. It does not silently move or suppress them.
