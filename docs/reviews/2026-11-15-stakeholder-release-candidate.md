# Stakeholder Brief release candidate (2026-11-15)

The split release agreed on 2026-11-15: the Stakeholder Brief, the theme fix
and the mobile arrow fix, shipped without P2 or the accuracy batch. Local and
uncommitted; no push, deploy, paid call or AWS change.

- Worktree: `C:\Users\ferna\cursor projects\side-projects\archibrief-release`
- Branch: `release/stakeholder-brief`, based on `e063dfd` (the live revision).
- `frontend/node_modules` is a junction to the main checkout's; remove the
  junction, not its target, with the worktree.
- Untracked files are marked intent-to-add (`git add -N`), so
  `git diff e063dfd` shows every change, new files included.

## What it contains

1. **Stakeholder Brief**: the captured `feat/stakeholder-brief` worktree,
   byte for byte (51 files: 17 new, 3 deleted, 31 modified). Details:
   `docs/reviews/2026-11-15-stakeholder-brief-implementation.md`.
2. **Theme fix**: the `fix/theme-before-paint` worktree applied as is
   (`app/layout.tsx`, `components/archibrief-app.tsx`, `app/globals.css`,
   `e2e/mobile-and-contrast.spec.ts`). The saved theme is applied before the
   first paint; light stays the default without a saved choice (decided
   2026-10-21).
3. **Brief-side repairs from Codex's integration**:
   - `.demo-strip { color: var(--text) }`, as in the integration (redundant
     with the theme fix, kept as a guard).
   - DLQ card: **not** the integration wording. That wording describes the
     accuracy batch's new rule ("the current check allows one day"), which
     this release doesn't include. The live rule fires when the dead-letter
     queue keeps messages for less time than its source queue, so the card
     keeps that description and only drops the old "up to 14 days"
     overpromise:
     "…keep messages longer than the main queue, within AWS's 14-day limit.
     If the main queue already keeps them for close to 14 days, keep failed
     jobs another way or change the retry process. Make sure someone watches
     it." When the accuracy batch ships, take the integration's wording with
     its rule.
4. **Mobile arrow fix** (`app/globals.css`, phone block): the tags box starts
   at zero width and grows (`flex: 1 1 0`), and the arrow never shrinks. A
   wrapping flex line moves an item down before shrinking it, which is why
   the arrow used to land on its own line. New test:
   `e2e/stakeholder-brief.spec.ts` "on a narrow phone each row's arrow stays
   on the severity line" (320 px, with an extra reviewer-correction tag). It
   failed before the fix (arrow 133 px below the severity mark).

## Release diff

`git diff --stat e063dfd`: 54 files (with this note).

- No `infra/`, `.tf` or `.github/` files change.
- Backend code changes reach exactly four Lambdas (from
  `scripts/package_lambdas.py`):

| Lambda | Changed modules packaged |
|---|---|
| get_review | `shared/report.py`, `shared/stakeholder/presentation.py` |
| deeper_review | `shared/report.py`, `lambdas/deeper_review/handler.py`, `shared/stakeholder/presentation.py` |
| ask_question | `chat/access.py`, `shared/money_policy.py` |
| list_questions | `chat/access.py`, `shared/money_policy.py` |

## Validation (this worktree)

- Backend `pytest -m "not coverage_gap"`: **1709 passed**, 13 skipped,
  8 deselected.
- `ruff format --check backend`, `ruff check backend`: pass.
- `scripts/build_demo_stakeholder.py --check`: 0.
- Frontend unit: **130 passed** (17 files). Typecheck, lint, format: clean.
- Full Playwright (`CI=1`): **84 passed, 0 failed**, including landing dark
  contrast, the theme regression test and the new arrow test.
- Lambda packages: built the four zips with
  `scripts/package_lambdas.py get_review deeper_review ask_question list_questions`
  (ignored `build/` folders). Each handler imports using only the `backend/`
  code inside its own zip; no backend module came from outside the package.
  Third-party libraries came from the local venv for that check, because the
  packaged `pydantic_core` is a Linux binary. A real cold start on Lambda's
  Linux runtime was not run.
- Screenshots: phone rows at 320 and 390 px in
  `C:\Users\ferna\AppData\Local\Temp\claude\99eb7ac7c4093561\05e09242-c67e-4844-9876-944668fa616c\scratchpad\shots\brief-rows-320.png`
  and `brief-rows-390.png`.

Not run: hosted CI, `terraform plan`, a deploy, a live smoke test.

## Deploy notes (need approval at each step)

The default branch is `master`. Merging is the frontend release:
`.github/workflows/deploy-frontend.yml` deploys to the `production`
environment after CI passes on `master`, and that environment has no
required-reviewer gate. So there is no separate frontend approval after the
merge, and the backend goes first:

1. PR #67 open; hosted CI green on its head commit.
2. Backend, before merging: build the four zips from this branch, run
   `terraform plan` for the dev environment. **The plan must change only the
   four functions' code (`source_code_hash` and `filename`).** Anything else,
   stop. Apply only with approval.
3. Merge PR #67 with approval. This deploys the frontend, followed by the
   workflow's own smoke test.
4. If the merge has to wait after the backend is applied, that's safe: the
   old frontend handles the new backend's reports and the reverse
   (ADR-0062 §9).
5. Rollback: the frontend redeploys from `e063dfd`; the Lambdas from zips
   built at `e063dfd`.
6. Smoke test: `node scripts/smoke_live.mjs https://archibrief.dev https://api.archibrief.dev`,
   then open a demo's Stakeholder tab in light and dark, and on a phone.

## Known limits carried into this release

From the brief handoff: the conditional wording on 17 concerns; unused
pricing code. None is a release blocker.

Scope of the no-prices change, stated exactly: generated chat answers and
transcripts (new, cached, suggested and read back) are filtered on the server,
and the displayed brief and both downloads are filtered in the browser. Raw
saved review data is preserved, and `get_review` still returns raw finding
fields. The model can still write a price; it is removed on output, not
prevented. The filter matches dollar patterns only, and keeps a bare `$`
plus a whole number in code as a likely positional variable. It is not a
guarantee that no amount can ever appear.
