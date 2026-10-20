"""Response headers every API Lambda sends.

API Gateway's HTTP API can't add response headers itself, so each
handler sends them. The API only ever returns JSON, so the headers are
strict: no MIME sniffing, HTTPS only, nothing cached and no referrer
leaked.
"""

from __future__ import annotations

JSON_HEADERS: dict[str, str] = {
    "content-type": "application/json",
    "x-content-type-options": "nosniff",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
}
