"""Make user-supplied values safe to write into a log line.

Logs are newline-delimited and read by humans and by log shippers. A value
carrying a newline lets whoever supplied it forge whole entries: an address of

    "Main St\\n2026-01-01 00:00:00 [INFO] auth: admin logged in from 10.0.0.1"

produces a second line that looks exactly like a real one. Nothing downstream
can tell the difference, which is the point of the attack.

Stripping the control characters removes the ability to forge a line break.
Truncating keeps one oversized field from pushing everything else out of a
rotated log. Quoting makes the boundaries of the value unambiguous, so a value
that merely *looks* like log syntax still reads as data.
"""

import re

# C0 controls plus DEL. Covers CR and LF, which are the ones that matter, and
# the rest because a terminal reading the log should not be driven by input.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

DEFAULT_LIMIT = 200


def for_log(value, limit: int = DEFAULT_LIMIT) -> str:
    """Return `value` as a single-line, length-capped, quoted string."""
    text = _CONTROL.sub("", str(value))
    if len(text) > limit:
        text = text[:limit] + "...(truncated)"
    return repr(text)
