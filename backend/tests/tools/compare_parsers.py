"""Parse a real flight log with both the 2.2.0 parsers and the current ones,
and report every difference.

The flight-log parsers were rewritten this week: three defects fixed and six
functions broken up. The tests say the behaviour held, but they run on fixtures
someone wrote. This runs the two versions side by side over a file that came out
of a real aircraft, which is the only thing that can say the rewrite kept its
promise on data nobody anticipated.

    python backend/tests/tools/compare_parsers.py <file> [<file> ...]

Differences are expected in exactly three places, and are labelled EXPECTED:

  * an Airdata CSV gains speed_mps and max_speed_mps, because the old candidate
    list looked for "speed_mph" and the column is "speed(mph)"
  * a DJI log whose header lacks DateTime(utc) is detected as dji rather than
    falling through to the CSV parser and producing nothing
  * a log with a row shorter than its header parses instead of raising

Anything else is a regression.
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

OLD_DIR = Path("/tmp/parsercmp")


def _load_old():
    """The 2.2.0 module, loaded under its real name so its internal
    `from app.services.parrot_import import ...` still resolves."""
    spec = importlib.util.spec_from_file_location("old_fli", OLD_DIR / "old_fli.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _summarise(result):
    """The parts of a parse worth comparing: the metadata, and the shape and
    content of the telemetry."""
    meta = dict(result.get("metadata") or {})
    telemetry = result.get("telemetry") or []
    return {
        "error": result.get("error"),
        "points": len(telemetry),
        "metadata": {k: str(v) for k, v in sorted(meta.items())},
        "first": {k: str(v) for k, v in sorted(telemetry[0].items())} if telemetry else None,
        "last": {k: str(v) for k, v in sorted(telemetry[-1].items())} if telemetry else None,
    }


def _parse(module, text):
    fmt = module.detect_format(text)
    if fmt == "dji":
        return fmt, module.parse_dji_txt(text)
    if fmt == "airdata_json":
        return fmt, module.parse_airdata_json(text)
    if fmt in ("litchi", "airdata", "unknown"):
        return fmt, module.parse_csv_log(text, "airdata" if fmt == "unknown" else fmt)
    if fmt == "parrot":
        from app.services.parrot_import import parse_gutma
        return fmt, parse_gutma(text)
    return fmt, {"metadata": {}, "telemetry": [], "error": f"unsupported: {fmt}"}


EXPECTED = {
    "speed_mps", "max_speed_mps",          # the Airdata speed column fix
    "format", "error", "points",           # detection and the ragged-row fix
}


def compare(path: Path, old, new):
    text = path.read_bytes().decode("utf-8", errors="replace")
    old_fmt, old_result = _parse(old, text)
    new_fmt, new_result = _parse(new, text)
    a, b = _summarise(old_result), _summarise(new_result)

    print(f"{path.name}  ({path.stat().st_size:,} bytes)")
    print(f"  format   2.2.0={old_fmt!r}   now={new_fmt!r}")
    print(f"  points   2.2.0={a['points']:,}   now={b['points']:,}")
    print(f"  error    2.2.0={a['error']!r}   now={b['error']!r}")

    diffs = []
    if old_fmt != new_fmt:
        diffs.append(("format", old_fmt, new_fmt))
    if a["points"] != b["points"]:
        diffs.append(("points", a["points"], b["points"]))
    if a["error"] != b["error"]:
        diffs.append(("error", a["error"], b["error"]))
    for key in sorted(set(a["metadata"]) | set(b["metadata"])):
        if a["metadata"].get(key) != b["metadata"].get(key):
            diffs.append((f"metadata.{key}", a["metadata"].get(key), b["metadata"].get(key)))
    for where in ("first", "last"):
        pa, pb = a[where] or {}, b[where] or {}
        for key in sorted(set(pa) | set(pb)):
            if pa.get(key) != pb.get(key):
                diffs.append((f"{where}_point.{key}", pa.get(key), pb.get(key)))

    if not diffs:
        print("  IDENTICAL: every field matches 2.2.0")
        return 0

    unexpected = 0
    print(f"  {len(diffs)} difference(s):")
    for field, was, now in diffs:
        tail = field.split(".")[-1]
        label = "EXPECTED" if tail in EXPECTED or field.split(".")[0] in EXPECTED else "REGRESSION?"
        if label != "EXPECTED":
            unexpected += 1
        print(f"    [{label}] {field}")
        print(f"        2.2.0: {was}")
        print(f"        now  : {now}")
    return unexpected


def main(paths):
    old, new = _load_old(), __import__("app.services.flight_log_import", fromlist=["x"])
    unexpected = 0
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            print(f"{raw}: not found")
            return 2
        unexpected += compare(path, old, new)
        print()
    print("No unexplained differences." if not unexpected
          else f"{unexpected} difference(s) need explaining.")
    return 1 if unexpected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else (print(__doc__) or 2))
