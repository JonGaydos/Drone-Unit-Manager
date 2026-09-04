# Phase 3 Tier A Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Pin base images to digests, add a Trivy image scan in CI, and add upload content-signature (magic-byte) validation.

**Architecture:** A new `file_validation` helper sniffs leading bytes; image-only upload handlers require an image signature, the documents handler rejects executables. Dockerfile pins both base images to `@sha256`. CI gains a non-blocking Trivy step.

**Tech Stack:** FastAPI/SQLAlchemy backend, Docker, GitHub Actions. Verify: `py_compile` + `import app.main` + seeded smoke test; CI build proves the Dockerfile.

**Branch:** `feat/tier-a-hardening` off `main`.

**Backend python:** `D:/Claude Projects/Drone-Unit-Manager/backend/.venv/Scripts/python.exe`, `PYTHONPATH=.` from `backend`.

---

### Task 0: Branch
- [ ] `git -C "D:/Claude Projects/Drone-Unit-Manager" checkout main && git -C "D:/Claude Projects/Drone-Unit-Manager" pull --ff-only && git -C "D:/Claude Projects/Drone-Unit-Manager" checkout -b feat/tier-a-hardening`

---

### Task 1: file_validation helper

**Files:** Create `backend/app/services/file_validation.py`

- [ ] **Step 1: Create the helper**
```python
"""Content-signature (magic-byte) sniffing for upload validation.

Best-effort detection from leading bytes. Used to block disguised uploads:
image-only handlers require an image signature; the documents handler rejects
positively-detected executables.
"""

IMAGE_TYPES = frozenset({"jpeg", "png", "gif", "webp", "bmp", "tiff"})
EXECUTABLE_TYPES = frozenset({"exe", "elf"})


def sniff_type(head: bytes) -> str | None:
    """Return a short type name for recognized leading bytes, else None."""
    if not head:
        return None
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:2] == b"BM":
        return "bmp"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:5] == b"%PDF-":
        return "pdf"
    if head[:2] == b"PK\x03\x04"[:2]:  # zip / docx / xlsx / pptx / odt
        return "zip"
    if head[:4] == b"\xd0\xcf\x11\xe0":  # legacy OLE doc/xls/ppt
        return "ole"
    if head[:2] == b"MZ":
        return "exe"
    if head[:4] == b"\x7fELF":
        return "elf"
    return None


def is_image(head: bytes) -> bool:
    """True if the leading bytes are a recognized raster image signature."""
    return sniff_type(head) in IMAGE_TYPES


def is_executable(head: bytes) -> bool:
    """True if the leading bytes look like a native executable (PE/ELF)."""
    return sniff_type(head) in EXECUTABLE_TYPES
```

- [ ] **Step 2: Compile + smoke**

Create `C:/Users/jgayd/.claude/plans/smoke_sniff.py`:
```python
from app.services.file_validation import sniff_type, is_image, is_executable
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PDF = b"%PDF-1.7\n..."
MZ = b"MZ\x90\x00" + b"\x00" * 16
SH = b"#!/bin/sh\necho hi\n"
assert sniff_type(PNG) == "png" and is_image(PNG)
assert sniff_type(JPG) == "jpeg" and is_image(JPG)
assert sniff_type(PDF) == "pdf" and not is_image(PDF)
assert sniff_type(MZ) == "exe" and is_executable(MZ) and not is_image(MZ)
assert sniff_type(SH) is None and not is_image(SH) and not is_executable(SH)  # script renamed .png -> rejected by image handlers
print("SNIFF_SMOKE_OK")
```
Run:
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/services/file_validation.py && PYTHONPATH=. .venv/Scripts/python.exe "C:/Users/jgayd/.claude/plans/smoke_sniff.py" && rm -f "C:/Users/jgayd/.claude/plans/smoke_sniff.py"
```
Expected: `SNIFF_SMOKE_OK`

- [ ] **Step 3: Commit**
```bash
git -C "D:/Claude Projects/Drone-Unit-Manager" add backend/app/services/file_validation.py && git -C "D:/Claude Projects/Drone-Unit-Manager" commit -m "feat(security): add file content-signature sniffing helper"
```

---

### Task 2: photos.py upload (streaming) — require image signature

**Files:** Modify `backend/app/routers/photos.py` (`upload_photo`, the write loop ~219-241)

- [ ] **Step 1: Validate the first chunk before writing.** Replace the write loop:

BEFORE:
```python
    total = 0
    chunk_size = 64 * 1024
    with open(file_path, "wb") as f:
        while True:
            chunk = file.file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > settings.MAX_UPLOAD_SIZE:
                f.close()
                os.remove(file_path)
                raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
            f.write(chunk)
```
AFTER:
```python
    from app.services.file_validation import is_image
    total = 0
    chunk_size = 64 * 1024
    first = file.file.read(chunk_size)
    if not is_image(first):
        raise HTTPException(400, "File content is not a recognized image")
    with open(file_path, "wb") as f:
        chunk = first
        while chunk:
            total += len(chunk)
            if total > settings.MAX_UPLOAD_SIZE:
                f.close()
                os.remove(file_path)
                raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
            f.write(chunk)
            chunk = file.file.read(chunk_size)
```

- [ ] **Step 2: Compile + import**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && .venv/Scripts/python.exe -m py_compile app/routers/photos.py && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('OK')"
```
- [ ] **Step 3: Commit** `git ... add backend/app/routers/photos.py && git ... commit -m "feat(security): reject non-image photo uploads via signature check"`

---

### Task 3: documents.py upload — reject executables

**Files:** Modify `backend/app/routers/documents.py` (`upload_document`, ~108-111)

- [ ] **Step 1:** Insert the check between the size check and the write:

BEFORE:
```python
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    dest.write_bytes(contents)
```
AFTER:
```python
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB")
    from app.services.file_validation import is_executable
    if is_executable(contents[:512]):
        raise HTTPException(400, "Executable file uploads are not allowed")
    dest.write_bytes(contents)
```
- [ ] **Step 2: Compile + import** (as Task 2 Step 2, for documents.py)
- [ ] **Step 3: Commit** `... -m "feat(security): block executable document uploads via signature check"`

---

### Task 4: settings.py logo upload — require image, validate before deleting old

**Files:** Modify `backend/app/routers/settings.py` (`upload_logo`, ~137-146)

- [ ] **Step 1:** Reorder so validation happens before the old logo is unlinked/written:

BEFORE:
```python
    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed for logo.")
    for old in upload_dir.glob("logo.*"):
        old.unlink()
    filepath = upload_dir / f"logo{ext}"
    content = await file.read()
    if len(content) > app_settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")
    await anyio.Path(filepath).write_bytes(content)
```
AFTER:
```python
    ext = Path(file.filename).suffix.lower() or ".png"
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(400, f"File type '{ext}' not allowed for logo.")
    content = await file.read()
    if len(content) > app_settings.MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large. Maximum size is {app_settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB")
    from app.services.file_validation import is_image
    if not is_image(content[:512]):
        raise HTTPException(400, "File content is not a recognized image")
    for old in upload_dir.glob("logo.*"):
        old.unlink()
    filepath = upload_dir / f"logo{ext}"
    await anyio.Path(filepath).write_bytes(content)
```
- [ ] **Step 2: Compile + import** (settings.py)
- [ ] **Step 3: Commit** `... -m "feat(security): validate logo upload signature before replacing existing logo"`

---

### Task 5: pilots.py + vehicles.py photo uploads — require image

**Files:** Modify `backend/app/routers/pilots.py` (`upload_pilot_photo`, ~216-218) and `backend/app/routers/vehicles.py` (`upload_vehicle_photo`, ~286-288)

- [ ] **Step 1:** In each, read the actual variable name holding the bytes (likely `content` or `contents`) and the size-check block, then insert immediately AFTER the size check, BEFORE the write:
```python
    from app.services.file_validation import is_image
    if not is_image(<bytes_var>[:512]):
        raise HTTPException(400, "File content is not a recognized image")
```
Replace `<bytes_var>` with the real name in each file. (Both read all bytes at once via `await file.read()`.)

- [ ] **Step 2: Compile + import** both files.
- [ ] **Step 3: Commit** `... add backend/app/routers/pilots.py backend/app/routers/vehicles.py && ... -m "feat(security): reject non-image pilot/vehicle photo uploads"`

---

### Task 6: Dockerfile base-image digest pinning

**Files:** Modify `Dockerfile` (lines 2 and 10)

- [ ] **Step 1: Resolve current digests** (manifest-list digests for the multi-arch tags):
```bash
echo -n "node:20-alpine -> " && curl -s "https://hub.docker.com/v2/repositories/library/node/tags/20-alpine" | python -c "import sys,json;print(json.load(sys.stdin)['digest'])"
echo -n "python:3.12-slim -> " && curl -s "https://hub.docker.com/v2/repositories/library/python/tags/3.12-slim" | python -c "import sys,json;print(json.load(sys.stdin)['digest'])"
```
If `python` is not on PATH, use the backend venv python. If the API is unreachable, STOP and report BLOCKED (do not invent a digest).

- [ ] **Step 2: Pin both `FROM` lines**, keeping the tag for readability and adding the digest + a bump comment:
```dockerfile
# Stage 1: Build frontend
# Base pinned to digest for reproducible builds. To bump: re-resolve with
# `curl -s https://hub.docker.com/v2/repositories/library/node/tags/20-alpine | jq -r .digest`.
FROM node:20-alpine@sha256:<NODE_DIGEST> AS frontend-build
```
```dockerfile
# Stage 2: Python backend + serve frontend
# Base pinned to digest. Bump: re-resolve library/python/tags/3.12-slim digest.
FROM python:3.12-slim@sha256:<PY_DIGEST>
```
Use the exact digests resolved in Step 1.

- [ ] **Step 3: Commit** `... add Dockerfile && ... commit -m "build(security): pin base images to digests"`
(The build is verified by CI on push; do not attempt a local docker build.)

---

### Task 7: Trivy image scan in CI (non-blocking)

**Files:** Modify `.github/workflows/docker-publish.yml`

- [ ] **Step 1: Add a Trivy step after the build-push step**, pinned to a commit SHA (resolve the latest `aquasecurity/trivy-action` release SHA; if you cannot resolve a SHA, use a pinned version tag and note it). Scan the first pushed tag:
```yaml
      - name: Scan image for vulnerabilities (Trivy)
        uses: aquasecurity/trivy-action@<SHA>  # pin to a release commit SHA
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:sha-${{ github.sha }}
          format: table
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: '0'   # non-blocking: report only, never fail the deploy
        continue-on-error: true
```
Note: the metadata step tags include `type=sha,prefix=` so the image is available as `:<sha>`; confirm the exact tag form (the `sha-` prefix vs bare sha) against the metadata config and use whichever the build produced. If unsure, scan `${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest` (present on main builds). `continue-on-error: true` plus `exit-code: '0'` makes this purely informational for now.

- [ ] **Step 2: Commit** `... add .github/workflows/docker-publish.yml && ... commit -m "ci: add non-blocking Trivy image scan"`

---

### Task 8: Verify + live retest

- [ ] **Step 1: Backend sanity**
```bash
cd "D:/Claude Projects/Drone-Unit-Manager/backend" && PYTHONPATH=. .venv/Scripts/python.exe -c "import app.main; print('BACKEND_OK')"
```
- [ ] **Step 2: Live retest (after deploy):**
  - Upload a normal JPEG/PNG photo → succeeds; rename a `.txt`/script to `.png` and upload → **400** "not a recognized image". Same for pilot photo, vehicle photo, org logo.
  - Upload a real PDF as a document → succeeds; rename an `.exe` to `.pdf` → **400** "Executable not allowed".
  - The image still renders and the logo still displays (no regression).
  - CI: the build succeeds with the pinned digests; the Trivy step runs and prints findings without failing the run.
- [ ] **Step 3: Finish** — `superpowers:finishing-a-development-branch` (merge/push when Jonathan approves).

---

## Self-review (against spec)
- A1 digest pinning → Task 6 (live-resolved, bump comment). ✓
- A2 Trivy non-blocking in CI, SHA-pinned → Task 7. ✓
- A3 magic-byte: image-only handlers require image (photos/logo/pilot/vehicle), documents reject executables → Tasks 2-5 via the Task 1 helper. ✓
- Conservative: documents allow text/csv/pdf/office; only executables rejected. Image handlers' allowed extensions are all sniffable, so legit images always pass. ✓
- No DB/frontend changes. ✓
- No placeholders except the two digests + Trivy SHA, which Task 6/7 resolve live (with explicit BLOCK-don't-invent instruction). ✓
