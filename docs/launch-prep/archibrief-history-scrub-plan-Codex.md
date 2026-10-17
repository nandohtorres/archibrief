---
created_by: Codex
contributors: [Fernando]
review_status: draft - read-only history audit; no rewrite authorized
created: "2026-10-16"
updated: "2026-10-16"
---

# ArchiBrief history cleanup plan

No history was rewritten, files deleted, branches pushed, remote refs changed,
Terraform run, or AWS called. This is an inventory and decision proposal, not
authorization to scrub. Repository copy retained for a local task commit;
delivery copy belongs in Leonardo `AI-Drafts/Codex/`.

## Scope and method

Inspected the 95 commits reachable from starting snapshot `8d391b0` with
`git rev-list 8d391b0`. For each commit, inspected added file-content lines via
`git diff-tree --root --no-commit-id --no-ext-diff -r -p --unified=0 <commit>`.
Only commit IDs, categories and paths are reported here: no actual distribution
hostname, private prose, credentials or matched excerpts are reproduced.

Case-insensitive candidate patterns:

| Category | Pattern / review rule |
|---|---|
| Distribution hostname | `\bd[a-z0-9]{8,}\.cloudfront\.net\b`; inspect whether this is this project's deployed distribution rather than an AWS documentation example. |
| Private-vault references | `Leonardo`, `private[- ]vault`, or `Work-Project-(Spec|System-Design|Build-Plan|Issues-Log|Cost-Log)` |
| Career/portfolio prose | `career|portfolio|recruit|hiring|interview`, excluding `docs/site/vendor/` |

These patterns locate candidates, not secrets. They are intentionally not a
full personal-data or credential detector. In particular, `resume` was excluded
after it incorrectly matched workflow pause/resume; vendored Mermaid text also
produced irrelevant prose hits. Private links and intentional public author
identity need separate human judgment. Commit messages, author emails, tags,
other branches, unreachable objects, release assets, PR refs, CI artifacts,
forks, remote caches and untracked files are not cleared by this scan.

The following are **commits adding/changing matching lines**, not a list of
every later commit whose inherited tree still contains them. Review full
snapshots as well before a scrub; deleting a line in the latest tree leaves its
earlier blobs reachable. The task's own new commits are outside this fixed
baseline and must be included in a later publication audit.

## Candidate commits and paths

### Distribution hostname: two commits

| Commit | Path |
|---|---|
| `e0f13a1f2545` | `infra/modules/api-gateway/variables.tf` |
| `5abbed95bec5` | `infra/modules/api-gateway/variables.tf` |

The hostname is an endpoint identifier, not itself an authentication secret.
Removing it does not close origin bypass; the public-access design addresses
that separately. This task does not modify infrastructure defaults.

### Private-vault references: fifteen commits

| Commit | Matching paths / grouped scope |
|---|---|
| `decc985a8a9a` | `.github/workflows/ci.yml`, `README.md`, `backend/lambdas/rule_engine/handler.py`, `infra/environments/dev/variables.tf`, `infra/modules/api-gateway/main.tf`, and ADRs/index under `docs/adr/` |
| `9ae3bf597ae5` | `backend/agent/nodes/reason.py`, `backend/corpus/{eval,normalize_pdf}.py`, corpus fixture/PDF tests, and API/IAM/S3-Vectors/Step-Functions infrastructure files |
| `500dacbc8b7f` | `docs/adr/Work-Project-ADR-0044-No-User-Accounts-Admin-Pre-Shared-Credential.md` |
| `b1b9468021b9` | `backend/agent/{reasoning_eval,validate_reasoning_eval}.py` |
| `a66ec2a35a69` | `backend/agent/reasoning_eval.py` |
| `2bf3b03dbf95` | `infra/modules/agentcore-runtime/{main,variables}.tf` |
| `3f195f8e1693` | `backend/agent/build_runtime_package.py`, `infra/modules/step-functions-lambda/main.tf` |
| `4ba2b0e227d7` | `backend/agent/runtime_entrypoint.py`, handlers for clarify/deeper/finalize/get_demo/get_review, `backend/shared/report.py`, finalize tests |
| `4db4be5c2e0c` | `frontend/app/layout.tsx`, `frontend/components/archibrief-app.tsx`, fixture/live-admin E2E specs, `frontend/lib/{api,contracts}.ts` |
| `e0f13a1f2545` | dev infrastructure README/main/example tfvars, API main/variables, Step Functions main, `scripts/package_lambdas.py` |
| `e3150d5ae6d7` | `README.md`, `docs/architecture.md`, `docs/threat-model.md` |
| `c817c1992872` | `.gitleaks.toml` |
| `b81c0d0f70fa` | `tests/backend/traps/test_rule_engine_traps.py` |
| `5ac5c29693c9` | `docs/adr/Work-Project-ADR-0045-Archive-Path-Direct-Upload.md` |
| `a6242481bcc5` | `backend/shared/citations.py` |

Some hits are only note names in comments, legitimate public ADR history, or
scanner configuration. Do not remove technical evidence mechanically just
because it mentions a private source. Replace inaccessible dependencies with
self-contained public explanations where needed; preserve licenses and accepted
decision history. Current protected-path changes belong to their owner.

### Career/portfolio prose: four commits

| Commit | Matching paths |
|---|---|
| `decc985a8a9a` | ADRs 0004/0006/0007/0008/0010/0015/0016/0018/0021/0024/0025/0037/0041, ADR index, `docs/site/index.html` |
| `9ae3bf597ae5` | `backend/corpus/ingest.py`, ADRs 0021/0037 and index, `docs/site/index.html` |
| `500dacbc8b7f` | ADR-0044, `docs/site/progress.html`, `infra/modules/frontend-hosting/variables.tf` |
| `5ac5c29693c9` | ADR-0046 and ADR index |

These are candidates for editorial review, not proof of confidential career
content. Distinguish ordinary project motivation from personal job-search
strategy. An exact match list should be reviewed privately before selecting
replacements; do not paste private excerpts into public issues or PRs.

## Options

| Option | What it achieves | Cost / limitation |
|---|---|---|
| Forward-only cleanup in this repo | Public current tree becomes self-contained; preserves engineering history and existing references. | Earlier text remains visible in Git. Appropriate only if Fernando accepts its visibility. |
| `git filter-repo` in a disposable fresh clone | Remove selected historical paths or replace exact approved strings while preserving much of the progression. | Rewrites affected commit IDs and signatures; all parallel work must be frozen and coordinated. Text replacement can damage source/tests; renamed paths, messages, tags and other refs require explicit scope. |
| Clean snapshot in a new repository | Publish an audited source tree as a new root, with license/provenance and an explicit history-start note. | Loses historical engineering evidence; does not erase the original repository, forks, cached views or clones. Keep original private if desired. |

Recommendation: use forward-only cleanup if the candidates are nonsecret and
acceptable as history. Prefer a targeted filter-repo rehearsal only when the
owner requires specific old text to be absent while retaining history. Use a
clean snapshot when simplicity outweighs that evidence, not as a claim that
old copies have been erased. The earlier checkpoint favored retaining this
repository; this inventory alone does not establish a credential exposure that
overturns that judgment.

[git-filter-repo's documentation](https://github.com/newren/git-filter-repo/blob/main/Documentation/git-filter-repo.txt)
describes path/text filtering and fresh-clone safety. Its rewriting operations
are proposals only and were not executed here.

## Proposed procedure, requiring a separate explicit go-ahead

1. Freeze Claude/Codex work and choose the complete ref set and publication
   destination. Inventory branches/tags, remotes, PR refs, releases and artifacts
   without printing sensitive matches. Obtain the owner's approved exact path
   and text replacement list; enumerate renamed historical paths.
2. If an actual credential is found, revoke/rotate it first. History cleanup is
   not remediation for a live credential. Record evidence privately, with
   redacted scanner output. This task found metadata/prose candidates, not a
   demonstrated credential compromise.
3. Preserve an access-controlled backup outside the publication destination.
   Rehearse the selected approach in a fresh disposable clone, never in either
   agent's active worktree. Do not use `--force` to bypass a fresh-clone warning.
4. For filter-repo: apply reviewed exact-string/path/message rules, retain a
   private old-to-new commit map, and audit all intended refs for remaining
   matches. For a clean snapshot: copy only the audited tracked tree, exclude
   `.git`, credentials, generated artifacts and private drafts, preserve required
   upstream licenses, then create the new root only after approval.
5. Compare the resulting tree with the approved source except for intended
   redactions. Run secret scanning across all selected history and a current-tree
   scan; separately review prose, authorship metadata and endpoint identifiers.
   Rerun backend/frontend/browser checks, without deployment or paid evals.
6. Present the resulting diff, scan coverage, commit/ref map and remaining
   accessibility failures for review. Publishing, changing repository visibility,
   force-pushing/replacing remote refs, deleting backups and re-cloning active
   worktrees each require explicit authorization. None is implied by this plan.
7. If already exposed, coordinate collaborator clones, forks, PR refs, CI
   artifacts and host caches. [GitHub's sensitive-data guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
   explains why rewriting your local branch is insufficient. Avoid merging old
   history back into the cleaned repository.

## Remaining uncertainty

This is a read-only local history triage, not a comprehensive clearance for
publication. It has no remote-state knowledge and does not establish that
unreachable objects, provider logs or other devices are clean. Re-run the
inventory on the final integrated branch, including launch-prep documents and
Claude's parallel changes. Decide which draft material belongs only in the
private vault before publishing any repository copy.
