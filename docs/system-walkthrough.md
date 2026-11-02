# System walkthrough: one review, end to end

A guided tour for someone seeing ArchiBrief for the first time: what happens
between "Start review" and the report, where each guarantee comes from, and
what happens when something fails. [Architecture](architecture.md) is the
reference; this is the story. Decision records are linked as ADR-NNNN.

## The shape of it

```mermaid
flowchart TB
    subgraph Browser["Visitor's browser"]
        UI["Next.js static app<br/>review keys in localStorage"]
    end

    subgraph Edge["Edge"]
        CF["CloudFront + S3<br/>static site"]
        WAF["AWS WAF<br/>rate rule, body limit,<br/>managed rules"]
        API["API Gateway REST<br/>api.archibrief.dev"]
    end

    subgraph Admission["Admission (Lambda)"]
        Upload["create_upload<br/>Turnstile, upload limits,<br/>checksum-bound PUT URL"]
        Submit["submit_review<br/>exact upload check,<br/>spend reservation"]
    end

    subgraph Pipeline["Review pipeline"]
        SFN["Step Functions<br/>IDs and status only"]
        Worker["review_worker Lambda<br/>reads content from S3"]
        Stages["Ingest → Scan (Trivy) → RuleEngine<br/>→ Validate → Audit → Finalize"]
    end

    subgraph Reasoning["Bedrock AgentCore runtime (LangGraph)"]
        Graph["PreflightGate → Retrieve → Reason"]
    end

    subgraph Bedrock["Amazon Bedrock"]
        Claude["Claude Sonnet 4.6<br/>streamed, forced tool call"]
        Titan["Titan V2 embeddings"]
        GR["Guardrails"]
    end

    subgraph Stores["Storage"]
        S3["S3: uploads, jobs,<br/>evidence ledgers"]
        DDB["DynamoDB: reviews, findings,<br/>audit log, usage counters, questions"]
        Vec["S3 Vectors:<br/>AWS guidance corpus"]
        SSM["SSM: kill switch"]
    end

    UI --> CF
    UI --> WAF --> API
    API --> Upload
    API --> Submit --> SFN --> Worker
    UI -.->|PUT archive| S3
    Worker --> Stages
    Worker --> Graph
    Graph --> Titan
    Graph --> Vec
    Graph --> GR
    Graph --> Claude
    Stages --> S3
    Stages --> DDB
    Worker -.->|checked before paid work| SSM
```

Seventeen single-purpose Lambdas, one Standard state machine, one AgentCore
runtime, six DynamoDB tables, four S3 buckets (review data, the site, two
deployment-artifact buckets) and an S3 Vectors index. Everything
is Terraform in `infra/`.

## A review, step by step

```mermaid
sequenceDiagram
    autonumber
    actor V as Visitor
    participant UI as Browser app
    participant API as API Gateway + WAF
    participant S3 as S3
    participant SFN as Step Functions
    participant W as review_worker
    participant AC as AgentCore runtime
    participant BR as Bedrock

    V->>UI: Terraform archive, brief, regulatory answer
    UI->>API: POST /uploads (Turnstile token)
    API-->>UI: review ID, read/write keys, checksum-bound PUT URL
    UI->>S3: PUT archive (exact size and SHA-256, no overwrite)
    UI->>API: POST /reviews
    Note over API: verify the exact S3 version,<br/>reserve $0.40 against monthly, daily,<br/>visitor and review limits in one transaction
    API->>SFN: StartExecution (stable name: no double start)
    SFN->>W: review ID only
    W->>W: Ingest: static HCL parse, Guardrails on the brief
    W->>W: Scan: Trivy with no credentials, no network
    W->>W: RuleEngine: findings, diagram, resource summary
    Note over UI,W: the progress screen already shows the diagram
    W->>AC: invoke (one attempt, up to 600 s)
    AC->>BR: embed brief + up to 10 topic searches
    AC->>BR: Guardrails, then streamed Converse
    BR-->>AC: tool call: up to 12 findings
    AC->>AC: verify every quote against retrieved chunks
    AC-->>W: rule + verified model findings
    W->>W: Validate, Audit, Finalize (evidence ledger to S3)
    UI->>API: GET /reviews/{id} (read key)
    API-->>UI: report, diagram, guided costs, analysis quality
```

What each step guarantees:

| Step | Guarantee | Where |
|---|---|---|
| Upload | The bytes reviewed are exactly the bytes uploaded: size, SHA-256 and `If-None-Match: *` are signed into the URL | `backend/shared/uploads.py` |
| Submit | Money is reserved before any paid call, in one DynamoDB transaction across four scopes (month, day, visitor, review); a retry can't start a second run | `backend/shared/admission.py`, ADR-0052 |
| Workflow | Briefs and findings never enter Step Functions history; it carries IDs and status | ADR-0028 |
| Ingest | Terraform is parsed, never executed; remote modules are never fetched | ADR-0027 |
| Scan | Trivy runs boxed in: no AWS credentials, no network, module sources rewritten | ADR-0048 |
| RuleEngine | Deterministic findings that don't depend on the model or the brief | `backend/lambdas/rule_engine/` |
| Summary | The model gets facts, not code: allowlisted settings and fixed-vocabulary details, so no free text from the submission reaches it except capped names | ADR-0049, ADR-0056 |
| Reason | Every model quote must match a retrieved chunk; the model can only call `emit_findings` | ADR-0038 |
| Report | Rejected-output counts travel with the report; a rules-only report says so | `backend/shared/analysis_quality.py` |

## When things go wrong

| Failure | What the visitor sees | Why that's the right behavior |
|---|---|---|
| Turnstile fails or limits are reached | The form explains and nothing is charged | Fail closed before any cost |
| The archive is invalid | A clear failure; the reservation is given back | Nothing billed yet |
| Guardrails blocks the brief | "Flagged by our safety checks" | Guardrails was billed; the reservation stays |
| Trivy fails | The review continues with ArchiBrief's own rules and says the scanner didn't run | A scanner outage shouldn't block a review (ADR-0048) |
| The model fails or runs long | If the call fails or hasn't answered within 400 s, the review finishes with the rule findings and a note that the AI analysis didn't finish | Some evidence beats none; never retried, so never charged twice (ADR-0058, ADR-0059) |
| A model finding cites a quote that isn't in the evidence | That finding is dropped; the report counts it | One bad citation doesn't discard the review |
| Spend nears the monthly AWS budget | At 90% the kill switch turns itself on; every paid path refuses | Billing lags, so the $75 admission ceiling is the real-time limit (ADR-0052) |
| A deeper review times out | The job shows failed; reloading recovers its status | One model attempt per request |

## Cost control in layers

```mermaid
flowchart LR
    A["Turnstile<br/>is it a person?"] --> B["WAF<br/>per-IP rate, body size"]
    B --> C["Upload limits<br/>40/day, 6 per visitor"]
    C --> D["Spend reservation<br/>month $75, day $8,<br/>visitor $2, review $1"]
    D --> E["Kill switch<br/>checked before paid work"]
    E --> F["Per-call bounds<br/>max tokens, 12 findings,<br/>400 s, no retries"]
    G["AWS budget $100<br/>90% turns the kill switch on"] -.-> E
```

Each layer bounds a different failure: bots, floods, one visitor, one review,
an incident, a runaway call. Reservations are estimates, not a billing
ceiling; the AWS budget is the backstop for what admission doesn't see.

## Where the model is kept honest

```mermaid
flowchart TB
    In["Untrusted: Terraform, brief"] --> P["Static parse only<br/>(nothing executes)"]
    P --> S["Resource summary<br/>allowlists, fixed vocabulary,<br/>32-char names"]
    In --> G1["Guardrails at Ingest"]
    G1 --> G2["Guardrails before Reason"]
    S --> M["Model: data fields only,<br/>brief claims unverified,<br/>one schema-checked tool"]
    G2 --> M
    M --> V["Server checks: quote must match<br/>a retrieved chunk, type rules,<br/>no prices in model text"]
    V --> R["Report: provenance shown,<br/>rejections counted"]
```

No single layer is trusted to stop prompt injection. The structural ones
(nothing executes, no free text in the summary, no tool that changes
anything, server-side verification) hold even if the model is fooled
(ADR-0038, [threat model](threat-model.md)).

## Delivery

- **Frontend:** merge to `master` → CI → `deploy-frontend.yml` publishes
  that exact revision through an OIDC role that can only write the site
  bucket and invalidate CloudFront (ADR-0055). A daily smoke checks the live
  site with no credentials.
- **Backend:** the owner builds the Lambda and AgentCore packages, reviews a
  `terraform plan` and applies it. CI never touches backend infrastructure.
- **Quality gates on every PR:** backend tests (pytest and moto, including
  the trap and adversarial suites), frontend unit tests, Playwright with
  accessibility checks, Terraform lint and Trivy over our own infra, and
  Gitleaks.
