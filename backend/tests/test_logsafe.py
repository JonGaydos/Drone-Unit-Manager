"""A value from a request must not be able to forge a log line."""

from app.logsafe import DEFAULT_LIMIT, for_log

CR = chr(13)
LF = chr(10)


def test_a_newline_cannot_forge_a_second_line():
    """The whole point. Without this, the value below produces a line that
    looks exactly like a genuine INFO entry."""
    forged = "Main St" + LF + "2026-01-01 00:00:00 [INFO] auth: admin logged in"

    out = for_log(forged)

    assert LF not in out
    assert out.count(LF) == 0
    assert "Main St" in out


def test_carriage_returns_go_too():
    """A bare CR rewrites the current line on a terminal, hiding what came
    before it."""
    assert CR not in for_log("before" + CR + "after")


def test_every_c0_control_and_del_is_removed():
    payload = "".join(chr(c) for c in list(range(0x00, 0x20)) + [0x7F])

    out = for_log("a" + payload + "b")

    assert out == repr("ab")


def test_ordinary_text_survives_intact():
    assert for_log("1 Example Rd, Example City, FL 32000") == repr(
        "1 Example Rd, Example City, FL 32000")


def test_the_value_is_quoted_so_it_reads_as_data():
    """A value that mimics log syntax should still be visibly a value."""
    out = for_log("2026-01-01 [ERROR] something")

    assert out.startswith("'") and out.endswith("'")


def test_an_oversized_value_is_truncated():
    out = for_log("x" * (DEFAULT_LIMIT + 500))

    assert "truncated" in out
    assert len(out) < DEFAULT_LIMIT + 60


def test_a_value_at_the_limit_is_not_truncated():
    out = for_log("x" * DEFAULT_LIMIT)

    assert "truncated" not in out


def test_non_strings_are_accepted():
    """Callers log whatever they have; None and ints must not raise."""
    assert for_log(None) == repr("None")
    assert for_log(42) == repr("42")


def test_the_limit_is_adjustable():
    assert "truncated" in for_log("abcdefghij", limit=5)
