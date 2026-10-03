"""Hits the real services. Skipped by default; run with `pytest -m live`."""
from datetime import datetime, timedelta, timezone

import pytest

from dbw import registry
from dbw.providers import build_providers
from dbw.providers.base import NoData

pytestmark = pytest.mark.live


@pytest.mark.parametrize("source", sorted(build_providers()))
def test_source_reachable_for_recent_date(source):
    box = next(b for b in registry.load() if b.id == "eilat")
    day = datetime.now(timezone.utc).date() - timedelta(days=5)
    r = build_providers([source])[source].fetch(box, day)
    assert not (isinstance(r, NoData) and not r.reachable), r.reason


def test_gibs_true_colour_underlay_returns_a_real_image():
    from dbw.providers import gibs
    day = datetime.now(timezone.utc).date() - timedelta(days=2)
    img, why = gibs.fetch_image((31.0, 32.5, 33.5, 35.0), day)
    assert img is not None, why
    assert img.shape[2] == 3 and img.std() > 2.0


def test_telegram_token_works_and_the_bot_answers_getupdates():
    """Needs DBW_TELEGRAM_TOKEN in the environment (never in the repo). Reads only: it sends nothing and prints no token."""
    import os
    from dbw.channels import telegram
    if not os.environ.get("DBW_TELEGRAM_TOKEN"):
        pytest.skip("DBW_TELEGRAM_TOKEN is not set")
    chats = telegram.chats_from_updates(telegram.get_updates(telegram.load_token()))
    assert isinstance(chats, list)
