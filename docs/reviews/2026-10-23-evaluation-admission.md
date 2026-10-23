# Evaluation admission and attempt accounting

Scope follows Fernando's clarification: internal paid-test controls remain in
scope; report monetary amounts, cost labels, effort estimates and remediation
aggregation are deferred. No paid evaluation was executed.

## Implemented

All five validation/evaluation CLI entrypoints support a free preview and require
both confirmation and an explicit call cap before constructing cloud clients.
This closes the three older commands that previously relied only on available
credentials. Planned upper bounds include embedding, vector queries, guards and
model calls; oversized selected scopes are rejected before client construction.

A shared evaluation-only meter checks each next call. SDK retries are disabled;
request arguments and model output size are bounded; a dispatch deadline prevents
new calls. A unique journal records admission before invoking the client and
keeps failed/uncertain attempts counted. Existing files cannot be overwritten.
No raw prompt, answer or exception text is stored in that journal.

Returned usage is allowlisted. Structured Converse usage is retained even when
the client rejects truncated/malformed output, using the SDK's existing
[after-call event mechanism](https://docs.aws.amazon.com/boto3/latest/guide/events.html).
A real botocore Stubber test proves usage survives output rejection. Unknown
usage remains null rather than being invented from prompt length.

Failed/not-run reasoning, chat and retrieval cases remain visible in their
scheduled denominators. Later cases are retained after an exception. Incomplete
chat runs fail a completion gate; failed reasoning trap verdicts and execution
failures produce nonzero exits. Failed-call cost/latency is unknown, not zero;
the existing measured cost metric names its measured-attempt denominator.
Reasoning mode is explicitly a controlled model component, not a production
workflow/graph score. Frozen cases and answer keys are unchanged.

## Limits and remaining work

P09 is **partial**. These controls cap client attempts and request shape, not
dollars: `monetary_limit_enforced` is false in every plan/journal. They do not
provide a total token ceiling, authoritative service prices, complete billable
unit accounting or a hard interruption of an in-flight call. No new price table
or report cost calculation was added. Actual paid scope still requires explicit
operator authorization and reviewed configuration.

P07 semantic-oracle execution, full P08 production parity/whole-output grading,
versioned run manifests, full merged development/holdout retrieval evaluation and
P11–P16 typed coverage expansion remain open. The legacy single-query diagnostic
helpers remain library functions; CLI execution is the guarded operator entry.

## Validation

- 129 focused tests passed, including all five denied-admission/previews,
  dispatch/request/output bounds, immutable journals, failure usage capture,
  all-attempt denominators and trap exit status.
- All five `--plan` commands ran without AWS clients or chargeable calls.
- Full backend: 1,143 passed, 5 skipped, 26 documented coverage gaps deselected.
  Ruff checks and backend formatting passed.
- Report price/effort files, saved demos and the frozen answer key are unchanged.
