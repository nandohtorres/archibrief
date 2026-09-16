import hmac
import os


def handler(event: dict, _context: object) -> dict:
    expected = os.environ.get("ADMIN_KEY", "")
    provided = event.get("headers", {}).get("x-admin-key", "")
    is_authorized = bool(expected) and hmac.compare_digest(provided, expected)
    return {"isAuthorized": is_authorized}
