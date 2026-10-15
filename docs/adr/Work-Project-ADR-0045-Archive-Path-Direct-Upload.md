---
title: "ADR 0045: archive_path Resolved via Direct Upload — GitHub-Fetch Deferred"
type: decision
tags: [adr, project, work-project, archibrief, security]
created: "2026-10-12"
updated: "2026-10-12"
status: accepted
---

# ADR 0045: `archive_path` Resolved via Direct Upload — GitHub-Fetch Deferred

**Status:** Accepted (2026-10-12)

## Context

`backend/lambdas/ingest/handler.py` has always expected a local
filesystem path (`archive_path`) pointing at an already-present tar
archive, opened directly via `tarfile.open(archive_path, "r:*")`. No
client could ever have correctly supplied this — there is no path on
a Lambda's own ephemeral `/tmp` that is meaningful to a remote caller.
This was flagged repeatedly (Work-Project-Issues-Log.md, 2026-10-01
entries) as the one real gap stopping a submitted review from actually
working end to end: the frontend only ever collected a free-text
"Terraform repository reference" string, and nothing anywhere turned
that string, or anything else, into a real archive Ingest could open.

Closing this gap means deciding how ArchiBrief actually gets the
user's Terraform content — a real trust-boundary decision (what can
reach out to, or be reached by, this pipeline), not a wiring fix. Per
this project's established pattern (every prior trust-boundary
expansion — ADR-0027 untrusted ingestion, ADR-0038 prompt-injection
boundaries — got its own ADR before being built), this was explicitly
held open rather than guessed. Fernando made the call 2026-10-12.

Two real options were considered:

1. **Direct upload.** The client uploads its own archive straight to
   S3 via a presigned POST; ArchiBrief never makes an outbound network
   call to anywhere client-controlled.
2. **Server-side GitHub fetch.** The client supplies a repository
   reference (matching the UI's existing copy exactly); ArchiBrief
   fetches the tarball itself from GitHub.

## Decision

**Direct upload, built now. GitHub-fetch deliberately deferred, not
built — see "Deferred: GitHub-fetch" below for what it would need.**

Reasoning:

- **Buildable correctly today, with no new unmitigated attack
  surface.** Direct upload adds no outbound-fetch capability to any
  Lambda — nothing in the pipeline makes a network call to a
  client-supplied target. GitHub-fetch is a textbook SSRF shape (a
  server making outbound requests to attacker-influenced input) that
  needs real hardening — domain allowlisting, immutable-SHA
  enforcement, redirect refusal, size/timeout caps — to be safe, and
  that hardening is real, non-trivial work that deserves its own
  focused pass, not something to rush alongside everything else this
  session.
- **Keeps the product's own stated boundary intact.** The submission
  screen already says *"ArchiBrief statically reviews the code — it
  never runs Terraform or accesses your live AWS account."* Upload-only
  keeps that literally true in the broadest sense: nothing server-side
  reaches out anywhere. GitHub-fetch would quietly add a new kind of
  reach (to GitHub) that the current copy doesn't account for.
- **Still produces a fully real, working demo.** The output — a real,
  cited report from real submitted Terraform — is identical regardless
  of how the bytes arrived. Upload-only does not compromise the actual
  thing a reviewer of this project would look at.
- **This is not a permanent ceiling, just a sequencing choice.** Both
  options have lasting value for different cases (see Consequences) —
  this ADR picks what ships first, not a belief that upload is the
  only mechanism ArchiBrief should ever have.

### What was built

- `backend/shared/clients/__init__.py`: `S3Client.generate_presigned_post`
  — a presigned **POST**, not a bare PUT, specifically so S3 itself
  enforces a `content-length-range` condition (20 MB ceiling, a
  first-pass figure) before accepting the object, consistent with this
  project's existing pattern of bounding untrusted input at the
  earliest point (`extract_archive`'s member-count/path-traversal/
  symlink checks; the 400 KB DynamoDB item cap).
- `backend/lambdas/create_upload/handler.py` (new): backs `POST
  /uploads`, admin-gated like every other non-demo route. Takes the
  client's own pre-generated `review_id`, validates it against a
  conservative safe-character pattern (prevents S3-key injection via a
  crafted `review_id`, the same "treat client input as untrusted here
  too, not just at Ingest" instinct ADR-0038 already established),
  and returns a presigned POST scoped to `uploads/{review_id}/archive.tar`.
- `backend/lambdas/ingest/handler.py`: new `_resolve_archive_path()`
  downloads from S3 when given `archive_s3_key` (the real submission
  path going forward) and writes it to a local path before calling the
  existing, already-tested `extract_archive()` unchanged. `archive_path`
  itself is kept as a direct/lower-level entry point (tests, any future
  caller that already has a local file) — not removed, just no longer
  the only way in.
- Terraform: `POST /uploads` wired into `infra/modules/api-gateway`
  (its own least-privilege IAM role, `s3:PutObject` scoped to
  `uploads/*` only); Ingest's role gained a matching `s3:GetObject`
  scoped the same way; Ingest's Step Functions `Task` gained an
  explicit `Parameters` block (previously had none — received the
  whole state implicitly, which only ever "worked" because
  `archive_path` was never real client input to begin with).
- Frontend: `SubmitReviewRequest` gained a required `archive_s3_key`
  field; `submission-step.tsx` gained a real file input
  (`.tar`/`.tar.gz`, required only in live-API mode — the fixture flow
  needs no real file); `archibrief-app.tsx`'s submission handler now
  requests a presigned POST, uploads directly to S3, then submits the
  review with the resulting key.
- Both the reports bucket (already scoped to hold "submitted archives"
  per its own original module header, `infra/modules/s3/main.tf` —
  ADR-0007/0042) and the uploads/reports trust separation (a dedicated
  `uploads/` prefix, distinct from Finalize's trusted evidence-ledger
  writes) follow decisions this project had already made elsewhere,
  not new ones invented for this ADR.

## Deferred: GitHub-fetch

Not built. Written up here deliberately, so it reads as real planned
work, not a vague someday-TODO, when it's picked up.

**What it would add:** the client supplies `github.com/org/repo@commit`
(the UI already collects this string, purely as a display label
today); a Lambda fetches the tarball server-side instead of the client
uploading it.

**What it needs to be safe, not just functional:**

- **Immutable commit SHA only, never a branch/tag.** A branch could be
  force-pushed to point at something malicious *after* submission but
  *before* fetch — the existing UI copy ("immutable commit reference")
  already anticipated this; the fetch Lambda must actually enforce it
  (reject anything that isn't a 40-char hex SHA), not just hope for it.
- **Domain allowlist**, not an open fetch of any URL the client
  supplies — `github.com`/`codeload.github.com` only, resolved IPs
  checked against a private-range blocklist before the request goes
  out (classic SSRF mitigation: DNS rebinding can otherwise point an
  allowlisted hostname at an internal address at request time).
- **No following redirects blindly** — GitHub's own archive endpoints
  may redirect; any redirect target must be re-validated against the
  same allowlist, not trusted implicitly.
- **Size and timeout caps enforced before/while downloading**, not
  just after — an unbounded fetch is its own resource-exhaustion risk,
  distinct from the archive-bomb protections `extract_archive` already
  has for the *parsing* side.
- **A real scoping decision on private repos**: public repos need no
  credential at all (anonymous fetch works); private repos need a
  GitHub App installation or PAT, which is its own credential-
  management and authorization-scope question (which repos can this
  fetch reach?) — likely out of scope for a first pass regardless.
- **Its own adversarial regression tests** (ADR-0038 pattern): a
  branch reference, a redirect to a non-GitHub host, an oversized
  response, a non-200 response, DNS resolving to a private IP — each
  needs an explicit test, the same rigor already applied to
  `extract_archive`'s path-traversal/symlink/member-count suite.

**When to revisit:** once there's a concrete reason upload-only is
genuinely limiting — most plausibly, wanting continuous "review every
PR automatically" usage rather than one-off submissions, which is the
actual long-term value a VCS-integrated flow unlocks that upload never
will. Not before that hardening list above is actually planned to be
built, not just referenced.

## Consequences

- `archive_path` as a bare required field is gone from the real
  submission contract — `archive_s3_key` is now a hard requirement at
  the ASL layer (`infra/modules/step-functions-lambda/main.tf`'s
  "REQUIRED StartExecution Input shape" comment), same enforcement
  level `review_id`/`workload_brief` already had.
- `terraform_repo_ref` is now explicitly, permanently a display-only
  field unless/until ADR-0045's GitHub-fetch deferral is revisited —
  not a half-wired field anymore, a deliberately scoped one.
- The frontend's submission form now requires a real file selection
  before it will submit against a deployed API — fixture mode is
  unaffected (no file required, same as before).
- A new Lambda (`create_upload`) and a new IAM-scoped prefix
  (`uploads/`) exist that didn't before — both local-only Terraform
  edits, nothing applied, per the standing rule that real `apply`s are
  Fernando's to run.
- Updates required in the system design notes (API contracts
  section: `POST /uploads`, `SubmitReviewRequest`'s `archive_s3_key`)
  and the build plan (Phase 4/5 checklist items) — see
  Work-Project-Issues-Log.md's 2026-10-12 entry for the full build
  writeup and verification record.

## Full reasoning

Fernando, directly, 2026-10-12: asked which approach gets this
"launched," given limited time and the goal of a working, hireable
demo. Agreed direct upload is the pragmatic ship-now choice, explicitly
confirmed GitHub-fetch is the right *eventual* direction for continuous
usage, not a permanently inferior option — "both, honestly — they're
not really competing" was the framing landed on. Full exchange in this
session's conversation log.
