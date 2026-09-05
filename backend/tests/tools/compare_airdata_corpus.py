"""Parse every flight log in an Airdata export with the 2.2.0 parsers and the
current ones, and report every field that differs.

flight_log_import.py is the only import module that changed this week: three
defects fixed and six functions broken up. The unit tests say the behaviour
held, but they run on fixtures someone wrote, and a fixture written to match
the code proves nothing about the code. A real export is the check they cannot
be.

    python backend/tests/tools/compare_airdata_corpus.py <export.zip> [limit]

Reports a difference count per field. Anything non-zero outside the three
deliberate fixes is a regression.
"""
import collections
import importlib.util
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "backend"))

# The commit the running production image was built from.
BASELINE = "511d30a"


def _load_old(ref=BASELINE):
    """The parser as of `ref`, fetched from git so this needs no setup and
    says plainly which version it is comparing against."""
    source = subprocess.run(
        ["git", "show", f"{ref}:backend/app/services/flight_log_import.py"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    path = Path(tempfile.mkdtemp(prefix="parsercmp-")) / "old_fli.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("old_fli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    print(f"baseline: {ref} ({len(source.splitlines())} lines)")
    return module


def _parse(module, text):
    """Route the text the way import_flight_log would, and return the result."""
    fmt = module.detect_format(text)
    if fmt == "dji":
        return fmt, module.parse_dji_txt(text)
    if fmt == "airdata_json":
        return fmt, module.parse_airdata_json(text)
    if fmt in ("litchi", "airdata"):
        return fmt, module.parse_csv_log(text, fmt)
    if fmt == "unknown":
        return fmt, module.parse_csv_log(text, "airdata")
    if fmt == "parrot":
        from app.services.parrot_import import parse_gutma
        return fmt, parse_gutma(text)
    return fmt, {"metadata": {}, "telemetry": [], "error": f"unsupported: {fmt}"}


def _flatten(fmt, result):
    """Everything worth comparing, as a flat dict of strings."""
    out = {"_format": fmt, "_error": str(result.get("error"))}
    telemetry = result.get("telemetry") or []
    out["_points"] = str(len(telemetry))
    for key, value in (result.get("metadata") or {}).items():
        out[f"meta.{key}"] = str(value)
    # The ends of the track, plus one in the middle, which is where an
    # off-by-one in a rewritten loop would show.
    for label, index in (("first", 0), ("mid", len(telemetry) // 2), ("last", -1)):
        if telemetry:
            for key, value in telemetry[index].items():
                out[f"{label}.{key}"] = str(value)
    return out


def main(zip_path, limit=None):
    old, new = _load_old(), __import__("app.services.flight_log_import", fromlist=["x"])
    diffs = collections.Counter()
    examples = {}
    errors = []
    formats = collections.Counter()
    checked = empty = 0

    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".json", ".csv", ".txt"))]
        if limit:
            names = names[:int(limit)]
        total = len(names)
        for i, name in enumerate(names, start=1):
            if i % 100 == 0:
                print(f"  ... {i}/{total}", flush=True)
            try:
                text = z.read(name).decode("utf-8", errors="replace")
            except Exception as exc:            # noqa: BLE001 - report, do not stop
                errors.append((name, f"unreadable: {exc}"))
                continue
            try:
                a = _flatten(*_parse(old, text))
            except Exception as exc:            # noqa: BLE001
                a = {"_crash": f"{type(exc).__name__}: {exc}"}
            try:
                b = _flatten(*_parse(new, text))
            except Exception as exc:            # noqa: BLE001
                b = {"_crash": f"{type(exc).__name__}: {exc}"}

            checked += 1
            formats[b.get("_format", "?")] += 1
            if b.get("_points") == "0":
                empty += 1
            for key in set(a) | set(b):
                if a.get(key) != b.get(key):
                    diffs[key] += 1
                    examples.setdefault(key, (name, a.get(key), b.get(key)))

    print()
    print(f"files compared      {checked:,} of {total:,}")
    print(f"formats detected    {dict(formats)}")
    print(f"parsed to 0 points  {empty:,}")
    if errors:
        print(f"unreadable          {len(errors)}: {errors[:3]}")
    print()
    if not diffs:
        print("IDENTICAL. Every field matches 2.2.0 on every file.")
        return 0

    print(f"{len(diffs)} field(s) differ:")
    for key, count in diffs.most_common():
        name, was, now = examples[key]
        print(f"  {key:34} {count:>6,} file(s)")
        print(f"      e.g. {name}")
        print(f"      2.2.0: {was}")
        print(f"      now  : {now}")
    return 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]) if len(sys.argv) > 1 else (print(__doc__) or 2))
