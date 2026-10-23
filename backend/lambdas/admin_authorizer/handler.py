import hmac
import os


def handler(event: dict, _context: object) -> dict:
    expected = os.environ.get("ADMIN_KEY", "")
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    provided = headers.get("x-admin-key", "")
    is_authorized = bool(expected) and hmac.compare_digest(
        str(provided).encode(), expected.encode()
    )
    if "methodArn" in event:
        # Anonymous requests are allowed only on the separate REST API whose
        # stage has WAF. The legacy HTTP API always requires the admin key.
        rest_id = os.environ.get("PUBLIC_REST_API_ID", "")
        trusted_rest = bool(rest_id) and (event.get("requestContext") or {}).get("apiId") == rest_id
        public = os.environ.get("PUBLIC_ACCESS_ENABLED", "false").lower() == "true"
        return {
            "principalId": "admin" if is_authorized else "visitor",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": "Allow" if is_authorized or (trusted_rest and public) else "Deny",
                        "Resource": event["methodArn"],
                    }
                ],
            },
        }
    return {"isAuthorized": is_authorized}
