# Browser test results

Executed against source `8d391b0`, adding only the
`frontend/e2e/launch-*.spec.ts` files. No existing specs or components changed.
Evidence: [machine-readable summary](playwright-launch-summary.json).

## Coverage and result

- Full mocked suite: **54 passed, 2 failed, 0 skipped**, 56 total. Command from
  `frontend/`: `npx.cmd playwright test --workers=2 --reporter=json`.
- Both failures were the new landing-page axe contrast checks, one per theme,
  run while the walkthrough's opacity reveal could be transitioning. All 39
  existing tests and the other 15 new tests passed in that run.
- Final axe-only rerun: **6 passed**, with reduced motion set before navigation
  and fonts loaded before scanning. Command: `npx.cmd playwright test
  launch-accessibility --workers=2 --reporter=json`. The remaining 50 tests were
  not rerun after this axe-only adjustment; there is no claim of a single
  all-green full-suite run on the final specs.

The final axe cases cover landing, technical and guided reports in both themes,
using locked transitive `axe-core` 4.13.0 (already provided through Lighthouse).
No package manifests or lockfiles changed. Reduced motion makes the existing
walkthrough reveal all steps and avoids opacity-dependent contrast results.
No rules or selectors were excluded. This covers the reduced-motion rendering;
normal-motion animation accessibility still needs a separate human review.
Automated axe success is not full WCAG conformance; incomplete checks remain
manual review items in the JSON summary.

Other new coverage: actual Tab-only navigation into the sample/report and back,
arrow/Home report tabs, keyboard filtering; 320x568, 768x1024, 844x390 and
1920x1080 layouts; held network response with one request; offline, malformed,
429 and 503 responses followed by recovery; 80 findings with long tokens and
paragraphs at 320px, filtering and JSON download. Every API response is mocked;
there were no AWS calls. The held response tests waiting UI, not real bandwidth
or packet-loss emulation. Browsers use Playwright's default Chromium; this is
not Safari/Firefox or a screen-reader test.

## Failures and constraints retained for review

Setup problems unrelated to the product were fixed before the recorded runs:
PowerShell's execution policy blocked `npm.ps1` (hence `npm.cmd`/`npx.cmd`), the
test environment blocked build-time Google Fonts fetches, and the new axe spec
used `import.meta` in Playwright's CommonJS context. The first long-content spec
also had an invalid typed presentation property, corrected before the browser
tests ran.

The first new-spec run returned 12 passed / 5 failed: one contrast check plus
four retry tests using the wrong button label. Correcting those selectors made
all recovery tests pass in the full run. An intermediate axe stabilization
attempt waited on animation promises and timed out both technical-view cases;
that new-spec wait was removed. The final six axe cases passed.

No confirmed component defect remained after correcting test timing/selectors.
The early contrast observations are preserved rather than represented as fixed
product bugs. Build/test runtime was Node 24.14.0, outside the declared Node
20/22 support range; repeat on a supported runtime before release. Final new
specs passed TypeScript, ESLint and Prettier checks.
