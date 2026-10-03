"""Every test starts with no Telegram token and no way to reach Telegram: a test that wants either fakes it."""
import pytest


@pytest.fixture(autouse=True)
def no_telegram_by_accident(request, monkeypatch):
    monkeypatch.delenv("DBW_TELEGRAM_TOKEN", raising=False)
    if request.node.get_closest_marker("live"):
        return
    from dbw.channels import telegram

    def blocked(*a, **k):
        raise AssertionError("a test reached the real Telegram API; fake telegram._http")
    monkeypatch.setattr(telegram, "_http", blocked)
    monkeypatch.setattr(telegram, "_sleep", lambda s: None)


@pytest.fixture(autouse=True)
def no_dns_by_accident(request, monkeypatch):
    """The scheduled run checks DNS before fetching; offline tests answer it here (a test that wants a failure fakes it)."""
    if request.node.get_closest_marker("live"):
        return
    from dbw import cli
    monkeypatch.setattr(cli, "_resolve", lambda host, port: [()])
    monkeypatch.setattr(cli, "_sleep", lambda s: None)
