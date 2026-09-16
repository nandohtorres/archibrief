# /frontend/app

Next.js App Router entrypoint for the static/client-first ArchiBrief UI.
Interactive workflow components live in `/frontend/components`; API and
evidence-ledger contracts live in `/frontend/lib`. Unit tests mirror that
structure under `/tests/frontend`.

Without `NEXT_PUBLIC_API_BASE_URL`, the app runs the reviewable fixture flow.
With it, submission calls the deployed `POST /reviews` contract and reports
the expected limitation that status/clarification/deeper endpoints are not
deployed yet.
