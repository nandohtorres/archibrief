"""Response headers and the CORS wrapper every API Lambda uses.

API Gateway can't add response headers itself, so each handler sends them.
The API only ever returns JSON, so the headers are strict: no MIME sniffing,
HTTPS only, nothing cached and no referrer leaked. api_handler answers CORS
preflight, rejects untrusted origins before application code runs, and adds
these headers to every response it returns.
"""

from __future__ import annotations

import json
import os
from functools import wraps

JSON_HEADERS: dict[str, str] = {
    "content-type": "application/json",
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
}


def api_handler(function):
    @wraps(function)
    def wrapped(event, context, *args, **kwargs):
        headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
        origin = headers.get("origin")
        try:
            allowed = json.loads(os.environ.get("CORS_ALLOWED_ORIGINS", "[]"))
        except ValueError:
            allowed = []
        if origin and origin not in allowed:
            return {"statusCode": 403, "headers": dict(JSON_HEADERS), "body": ""}
        method = event.get("httpMethod") or (event.get("requestContext", {}).get("http") or {}).get(
            "method"
        )
        result = (
            {"statusCode": 204, "body": ""}
            if method == "OPTIONS"
            else function(event, context, *args, **kwargs)
        )
        response_headers = result.setdefault("headers", {})
        for name, value in JSON_HEADERS.items():
            response_headers.setdefault(name, value)
        if origin:
            response_headers.update(
                {
                    "access-control-allow-origin": origin,
                    "vary": "Origin",
                    "access-control-allow-methods": "GET,POST,OPTIONS",
                    "access-control-allow-headers": "content-type,x-admin-key,x-review-read-token,x-review-write-token",
                    "access-control-max-age": "300",
                }
            )
        return result

    return wrapped
