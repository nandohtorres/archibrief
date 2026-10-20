# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub: open the
repository's **Security** tab and choose **Report a vulnerability**. Don't
open a public issue for anything that could be exploited.

Include what you found, how to reproduce it, and what an attacker could do
with it. This is a one-person project, so responses are best effort: expect
an acknowledgement within a week.

## In scope

- The live site at <https://archibrief.dev> and its API
  (`api.archibrief.dev`).
- The code in this repository: the review pipeline, the API handlers, the
  Terraform in `infra/` and the frontend.
- Ways around the admin-key authorizer, the spending limits or the kill
  switch, prompt injection that makes the model act outside its review, and
  anything that exposes another review's data.

## Out of scope

- The deliberately vulnerable Terraform in the demo reviews and the test
  fixtures (`frontend/public/demos/`, `tests/backend/traps/`,
  `backend/lambdas/get_demo/`). Those are examples of what ArchiBrief finds.
- Volumetric denial of service, spam, and social engineering.
- Findings in third-party services (AWS, Cloudflare, GitHub) themselves.
- Missing security headers or best-practice suggestions with no concrete
  impact.

Please don't run tests that cost money at scale (for example, scripted
review or chat requests), access data that isn't yours, or degrade the
service for others.

Design decisions and accepted risks are documented in
[docs/threat-model.md](docs/threat-model.md).
