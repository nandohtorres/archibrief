import pytest
from botocore.exceptions import ClientError

from backend.shared.kill_switch import paid_work_allowed


class _FakeSsm:
    def __init__(self, value: str | None = None, error: Exception | None = None):
        self.value = value
        self.error = error

    def get_parameter(self, Name: str) -> dict:
        if self.error:
            raise self.error
        return {"Parameter": {"Name": Name, "Value": self.value}}


@pytest.fixture(autouse=True)
def _param_name(monkeypatch):
    monkeypatch.setenv("KILL_SWITCH_PARAMETER_NAME", "/archibrief/dev/kill-switch")


def test_allows_paid_work_when_switch_is_off():
    assert paid_work_allowed(_FakeSsm("false")) is True


@pytest.mark.parametrize("value", ["true", "TRUE", " true "])
def test_blocks_paid_work_when_switch_is_on(value):
    assert paid_work_allowed(_FakeSsm(value)) is False


def test_fails_closed_when_parameter_unreadable():
    assert (
        paid_work_allowed(
            _FakeSsm(
                error=ClientError(
                    {"Error": {"Code": "AccessDeniedException"}}, "GetParameter"
                )
            )
        )
        is False
    )


def test_fails_closed_when_parameter_name_not_configured(monkeypatch):
    monkeypatch.delenv("KILL_SWITCH_PARAMETER_NAME")
    assert paid_work_allowed(_FakeSsm("false")) is False
