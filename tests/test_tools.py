# tests/test_tools.py
import os

import pytest

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_empty_wardrobe

# suggest_outfit and create_fit_card's happy paths call the live Groq API.
# Skip those when no key is configured so the suite still runs offline.
requires_api = pytest.mark.skipif(
    not os.environ.get("GROQ_API_KEY"),
    reason="GROQ_API_KEY not set — skipping live LLM test",
)


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    # Failure mode: no listing matches the query → empty list, no exception.
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    # Use a ceiling that actually returns matches, then assert every result
    # respects it. (max_price=10 returns [], which would pass vacuously.)
    results = search_listings("jacket", size=None, max_price=50)
    assert len(results) > 0
    assert all(item["price"] <= 50 for item in results)


# ── suggest_outfit ────────────────────────────────────────────────────────────

@requires_api
def test_suggest_outfit_empty_wardrobe():
    # Failure mode: empty wardrobe → general styling advice, not a crash.
    item = search_listings("vintage graphic tee", size=None, max_price=50)[0]
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert result.strip()  # non-empty string, gracefully handled


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit():
    # Failure mode: missing/empty outfit → descriptive message, NOT an exception.
    # Deterministic guard — runs without calling the LLM.
    result = create_fit_card("", {"title": "Y2K Baby Tee", "price": 18.0})
    assert isinstance(result, str)
    assert result.strip()


def test_create_fit_card_whitespace_outfit():
    result = create_fit_card("   ", {"title": "Y2K Baby Tee", "price": 18.0})
    assert isinstance(result, str)
    assert result.strip()