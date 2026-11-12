# ADR 0061: Small-Workload Accuracy Pilot (50 Resource Declarations)

**Status:** Proposed (direction accepted 2026-11-10; implementation details
under precision review). Extends ADR-0027 (untrusted ingestion), ADR-0049
and ADR-0056 (resource summary), ADR-0059 (bounded model input). When
accepted, it supersedes ADR-0059's 120-resource summary cap for public
reviews.

## Context

The live hard tests (2026-10-28 to 10-30) showed that review quality is
bounded by what the model is shown. The 119-resource test still misses an
EU data-residency breach and four critical issues after the fixes in
ADR-0056 to ADR-0059. Large configurations hit several caps at once: 120
summary resources, 60 diagram nodes, observation byte limits, 40 rule
findings sent to the model and 12 model findings. The current report
warns that coverage may be partial but doesn't say how much was reviewed.

Review logs from 2026-10-12 to 11-02 show 11 completed model reviews at
about $0.07 to $0.22 each (about $0.17 on average, estimated from token
counts) and 75 s median model time. The only two submissions whose size
was recorded had 69 and 119 resources.

Options considered:

1. **Keep the 120 cap and improve extraction for everything.** Most
   effort, slowest feedback, and accuracy stays unmeasured.
2. **Raise caps and send more to the model.** More cost and latency, and
   the timeout incident (2026-10-29) showed where that leads.
3. **Narrow the scope, measure, then widen on evidence.** Chosen.

## Decision

1. **Audience and limit.** ArchiBrief targets developers reviewing small
   AWS workloads (startups, solo developers, students). A review accepts
   at most **50 resource declarations** in one root. Fifty is a provisional
   pilot boundary, not a definition of "small" or an accuracy guarantee.
2. **What counts.** One `resource` block in the selected root or a
   reachable local module counts once, identified by module address, type
   and name. A block with `count` or `for_each` counts once. The same local
   module called twice counts twice. Non-AWS resources (for example
   `random`, `tls`, `null`) count toward the limit and are shown as not
   analyzed; they never cause a rejection.
3. **Modules that can't be read.** Remote or unresolved modules are never
   downloaded or executed. If the known count is 50 or under, the review
   runs as a **labeled partial review** that names the unreadable modules
   and never calls the total complete.
4. **Reject before paying.** The count runs after safe parsing and before
   Guardrails, embeddings, vector search or generation. An oversized root
   gets a clear, actionable message and starts no paid call.
5. **Show exactly what was reviewed.** Reports state how many declarations
   were sent to the model out of the total, with reasons for any omitted.
6. **Measure before changing the model path.** A baseline against written
   answer keys comes first. A second, bounded AI pass that checks each
   finding against the configuration and its cited source is tested next,
   within the existing per-review spend reservation.
7. **Quality gates.** Pass/fail: Critical/High recall must not drop, zero
   fabricated citations or fact IDs, zero unsafe remediation. Precision
   and all-severity recall are reported, not gated, while the sample is
   small.
8. **Build order.** The count is recorded internally first and used to score
   the baseline; the visible "X of Y" and the enforced limit ship together, so
   visitors never see a limit that isn't enforced. The AI runtime confirms
   admission by reading our own stored record, never a count in the request.
   Reports created before the change can't start new "go deeper" work.
9. **Baseline checkpoint.** If the baseline catches under 80% of planted
   Critical/High issues, each miss is diagnosed (never extracted vs. seen but
   misreasoned) and extraction gaps are fixed before the second AI pass.
10. **Widening is a separate decision.** 75 or 100 declarations is
   considered only after the 50 limit is measured and stable, and needs
   its own ADR.

## Consequences

- Large configurations are rejected with a message to submit one smaller
  root. This trades breadth for accuracy that can be measured and stated.
- Many small real repositories use registry modules; partial reviews keep
  them usable, at the cost of reviewing less than the whole design.
- ArchiBrief's own infrastructure (154 resource blocks) is above the limit
  and would need to be reviewed one module at a time.
- The second AI pass adds at least one paid call per review. It ships only
  if the measured reduction in wrong findings justifies it.
- Evaluation spend is approved per batch; the first baseline batch is
  capped at $5.

The implementation plan, evaluation design and budgets are kept with the
private launch notes and summarized in [project history](../project-history.md#7-narrowing-scope-to-raise-accuracy-november-10-in-progress).
