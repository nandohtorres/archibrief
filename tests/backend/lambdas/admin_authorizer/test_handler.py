from backend.lambdas.admin_authorizer.handler import handler


def _event(admin_key: str | None) -> dict:
    headers = {"x-admin-key": admin_key} if admin_key is not None else {}
    return {"headers": headers}


def test_allows_matching_key(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "correct-horse-battery-staple")
    assert handler(_event("correct-horse-battery-staple"), None) == {"isAuthorized": True}


def test_denies_wrong_key(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "correct-horse-battery-staple")
    assert handler(_event("wrong-key"), None) == {"isAuthorized": False}


def test_denies_when_header_missing(monkeypatch):
    monkeypatch.setenv("ADMIN_KEY", "correct-horse-battery-staple")
    assert handler(_event(None), None) == {"isAuthorized": False}


def test_denies_when_admin_key_not_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_KEY", raising=False)
    assert handler(_event("anything"), None) == {"isAuthorized": False}
