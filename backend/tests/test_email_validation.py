"""The email shape check is a header-injection guard, so it must anchor hard.

Python's `$` matches before a trailing newline, so `^...$` accepts
"user@example.gov\\n". A stored address carrying a newline is the raw material
for SMTP header injection, and the user schema validates with this pattern and
nothing else. `\\Z` is the anchor that means end-of-string and only that.
"""

import pytest

from app.routers.notifications import EMAIL_RE
from app.schemas.user import _EMAIL_RE, _validate_optional_email

CR = chr(13)
LF = chr(10)

PATTERNS = [pytest.param(EMAIL_RE, id="notifications"),
            pytest.param(_EMAIL_RE, id="user-schema")]


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("address", [
    "a@b.co",
    "first.last@sub.example.gov",
    "user+tag@mail.example.com",
    "x@y.co.uk",
    "UPPER@EXAMPLE.GOV",
    "a@b-c.de",
])
def test_real_addresses_are_accepted(pattern, address):
    assert pattern.match(address)


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("address", [
    "a@b.co" + LF,
    "a@b.co" + CR + LF,
    "a@b.co" + LF + "Bcc: attacker@example.net",
    "a@b.co" + CR + LF + "Bcc: attacker@example.net",
])
def test_a_trailing_or_embedded_newline_is_rejected(pattern, address):
    """The injection case. With `$` instead of `\\Z` the first two of these
    pass, and an address with a newline reaches the mail layer."""
    assert not pattern.match(address)


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("address", [
    "a@b", "a@.c", "a@b.", "@b.c", "a@b c.d", "a b@c.d", "a@@b.c", "",
    "a@b..c",          # an empty DNS label is not a valid domain
])
def test_malformed_addresses_are_rejected(pattern, address):
    assert not pattern.match(address)


def test_the_user_schema_validator_raises_on_an_injected_newline():
    """Exercised through the validator the schema actually calls, not just the
    pattern, since that is what a request goes through."""
    with pytest.raises(ValueError):
        _validate_optional_email("a@b.co" + LF + "Bcc: attacker@example.net")


def test_the_user_schema_validator_still_allows_blank_and_none():
    assert _validate_optional_email(None) is None
    assert _validate_optional_email("") == ""


def test_the_pattern_is_linear_on_hostile_input():
    """The reason it changed shape at all: [^@\\s] includes ".", so the old
    pattern let the engine try every dot as the separator. 6.4KB of dot-heavy
    input took 67ms and quadrupled on each doubling."""
    import time

    hostile = "a@" + ("b." * 3200) + "c "
    start = time.perf_counter()
    _EMAIL_RE.match(hostile)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.05, f"took {elapsed:.3f}s; the backtracking is back"
