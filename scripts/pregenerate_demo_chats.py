"""Pregenerate the demos' suggested-question answers (ADR-0050 §7).

The demos are real stored reviews, so their suggested questions go
through the deployed chat once, on the admin path, and the answers are
saved next to the demo reports. Visitors then read them for free:

    frontend/public/demos/chats/<demo-id>.json

    python scripts/pregenerate_demo_chats.py --confirm-paid [demo-id ...]

Paid (one model call per suggestion the first time; a suggestion already
answered is served from storage for free), so never run without
Fernando's go-ahead in that moment. The admin key is read from Secrets
Manager (AWS_PROFILE) and never printed. Suggested questions don't use
any of a review's five questions.

Only the public transcript fields are saved; every value is the API's
own output, already verified server-side.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parent.parent
DEMOS = ROOT / "frontend" / "public" / "demos"
API = "https://api.archibrief.dev"
ADMIN_SECRET = "archibrief-dev-admin-key"
SAVED_FIELDS = (
    "suggested_id",
    "question",
    "status",
    "refusal_reason",
    "answer",
    "model_id",
    "prompt_version",
)


def _call(
    method: str, url: str, headers: dict, body: dict | None = None
) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        method=method,
        headers=headers,
        data=json.dumps(body).encode("utf-8") if body is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("demo_ids", nargs="*")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--api", default=API)
    args = parser.parse_args()
    if not args.confirm_paid:
        print(
            "Refusing to run: pass --confirm-paid (needs Fernando's go-ahead).",
            file=sys.stderr,
        )
        return 2

    key = boto3.client("secretsmanager").get_secret_value(SecretId=ADMIN_SECRET)[
        "SecretString"
    ]
    headers = {"x-admin-key": key, "content-type": "application/json"}
    demos = json.loads((DEMOS / "demos.json").read_text(encoding="utf-8"))["demos"]
    out_dir = DEMOS / "chats"
    out_dir.mkdir(exist_ok=True)

    for demo in demos:
        if args.demo_ids and demo["id"] not in args.demo_ids:
            continue
        report_path = DEMOS / "reports" / f"{demo['id']}.json"
        if not report_path.exists():
            print(f"{demo['id']}: no saved report, skipped")
            continue
        review_id = json.loads(report_path.read_text(encoding="utf-8"))["review_id"]
        url = f"{args.api}/reviews/{review_id}/questions"
        status, listing = _call("GET", url, headers)
        if status != 200:
            print(f"{demo['id']}: listing failed, HTTP {status}")
            continue
        answers = []
        for suggestion in listing["suggested"]:
            status, body = _call(
                "POST",
                url,
                headers,
                {
                    "client_request_id": str(uuid.uuid4()),
                    "suggested_id": suggestion["id"],
                },
            )
            if status != 200:
                print(f"{demo['id']} {suggestion['id']}: HTTP {status}")
                continue
            answers.append({field: body.get(field) for field in SAVED_FIELDS})
            print(f"{demo['id']} {suggestion['id']}: {body['status']}")
        (out_dir / f"{demo['id']}.json").write_text(
            json.dumps(
                {
                    "review_id": review_id,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "suggested": answers,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
