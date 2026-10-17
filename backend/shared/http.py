"""CORS for REST proxy responses; private credentials never enter caches."""

import json
import os
from functools import wraps


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
            return {"statusCode": 403, "headers": {"cache-control": "no-store"}, "body": ""}
        method = event.get("httpMethod") or (event.get("requestContext", {}).get("http") or {}).get(
            "method"
        )
        result = (
            {"statusCode": 204, "body": ""}
            if method == "OPTIONS"
            else function(event, context, *args, **kwargs)
        )
        response_headers = result.setdefault("headers", {})
        response_headers.setdefault("cache-control", "no-store")
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
