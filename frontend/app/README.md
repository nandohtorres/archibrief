# /frontend/app

Next.js App Router entrypoint for the static/client-first ArchiBrief UI.
Interactive workflow components live in `/frontend/components`; API and
evidence-ledger contracts live in `/frontend/lib`. Unit tests mirror that
structure under `/tests/frontend`.

Without `NEXT_PUBLIC_API_BASE_URL`, the app runs the reviewable fixture flow.
With it, the app talks to the deployed API: it uploads the archive
(`POST /uploads`), starts the review (`POST /reviews`), polls
`GET /reviews/{reviewId}`, and offers clarification, "go deeper" and the
report chat. Saved demo reviews under `/frontend/public/demos` work in both
modes without any API call.
