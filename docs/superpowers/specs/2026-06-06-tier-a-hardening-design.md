# Phase 3 Tier A — Hardening Design

Date: 2026-06-06
Project: Drone Unit Manager
Status: approved (one batch). Scope = Tier A only; SBOM/cosign, Alembic, and
JWT/PyJWT explicitly deferred.

## Context

Low-risk, high-value hardening surfaced by the code review: pin base images,
scan the image in CI, and validate upload content signatures. No DB changes, no
frontend.

## A1 — Base-image digest pinning

`Dockerfile` uses floating tags `node:20-alpine` and `python:3.12-slim`. Pin
both to immutable digests: `FROM node:20-alpine@sha256:<digest> AS frontend-build`
and `FROM python:3.12-slim@sha256:<digest>`. Digests are resolved live at
implementation time from the registry (Docker Hub tag API) so we pin today's
real images. Add a short comment above each `FROM` noting how to refresh the
digest on a future base bump.

- Tradeoff: digests freeze the image, so base-image patches require a manual
  digest bump. Acceptable at this cadence; documented in the comment.

## A2 — Trivy image scan in CI

Add a step to `.github/workflows/docker-publish.yml` after the build-push step,
using `aquasecurity/trivy-action` pinned to a commit SHA (matching the repo's
existing action-pinning convention). Config:
- scan the built/pushed image (the first tag from the metadata step),
- `severity: HIGH,CRITICAL`, `ignore-unfixed: true`,
- **non-blocking initially**: `exit-code: '0'` so findings are reported in the
  Actions log but never fail a deploy. (A follow-up can flip to `exit-code: '1'`
  on CRITICAL once the baseline is clean.)
- Optional: also produce SARIF and upload via `github/codeql-action/upload-sarif`
  to the Security tab (nice-to-have; include if it doesn't complicate the run).
- The job needs `security-events: write` permission only if uploading SARIF.

## A3 — Upload magic-byte validation

Add a content-signature check on top of the existing extension/MIME/size/path
checks, in the upload handlers (photos, documents, org logo — and media if it
shares the path). A small pure-Python helper reads the leading bytes and returns
a detected type:
- JPEG `FF D8 FF`, PNG `89 50 4E 47`, GIF `47 49 46`, WebP (`RIFF`…`WEBP`),
  PDF `%PDF`. (Images can also be confirmed with `Pillow.verify()`, already a
  dependency — no new system library.)
- Validation rule (**conservative**): if the claimed/allowed type is one we can
  sniff and the detected signature contradicts it, reject with HTTP 400. If the
  bytes match, or the type isn't one we sniff, allow (so legitimate but
  un-sniffed formats are never blocked). This blocks the disguised-upload case
  (e.g., a script renamed `.png`) without false-rejecting edge formats.
- Apply at the same point the current size/type check happens, before the file
  is written to disk.

## Non-goals
- No SBOM, no cosign signing (deferred).
- No Alembic migration adoption (deferred — risky on the live DB).
- No python-jose → PyJWT swap, no JWT revocation (deferred).

## Verification
- Backend: `py_compile` + `import app.main`; a seeded smoke test of the sniff
  helper (PNG bytes → detected png; `#!/bin/sh` bytes with a `.png` claim →
  rejected; a real PDF header → allowed) and that a normal image upload still
  succeeds.
- Docker/CI: the pinned `Dockerfile` builds (verified by the CI build itself);
  the Trivy step runs and reports without failing the build.
- Live: upload a renamed non-image as `.png` → 400; a normal photo/document/logo
  still uploads.

## Files (anticipated)
- `Dockerfile` (two `FROM` lines + comments).
- `.github/workflows/docker-publish.yml` (Trivy step, pinned).
- A small upload-signature helper (new util, e.g. `backend/app/services/file_validation.py`
  or inline in an existing upload util) + the upload handlers that call it
  (`routers/photos.py`, `routers/documents.py`, `routers/settings.py` logo,
  and `routers/media.py` if applicable).
