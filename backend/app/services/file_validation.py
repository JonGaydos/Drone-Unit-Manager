"""Content-signature (magic-byte) sniffing for upload validation.

Best-effort detection from leading bytes. Used to block disguised uploads:
image-only handlers require an image signature; the documents handler rejects
positively-detected executables.
"""

from pathlib import Path

IMAGE_TYPES = frozenset({"jpeg", "png", "gif", "webp", "bmp", "tiff"})
EXECUTABLE_TYPES = frozenset({"exe", "elf"})

# Content types the server assigns from a file's allowlisted extension. The
# browser-supplied Content-Type is never stored or served: an uploader could
# label any bytes text/html and have them render as a page on this origin.
_MIME_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp",
    ".tiff": "image/tiff", ".tif": "image/tiff",
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
}
OCTET_STREAM = "application/octet-stream"

# Sent with every user-uploaded file. Opened directly in a tab, the file can run
# no script and load nothing. PDFs are exempt: sandbox disables the browser's
# built-in PDF viewer, and that viewer does not run page script on this origin.
USER_FILE_CSP = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"


def mime_for_filename(name: str) -> str:
    """Server-assigned content type for a stored file, from its extension."""
    return _MIME_BY_EXT.get(Path(name).suffix.lower(), OCTET_STREAM)


def is_inline_safe(mime: str) -> bool:
    """True for types that may be shown inline: PDFs and raster images."""
    return mime == "application/pdf" or mime.startswith("image/")


def user_file_headers(mime: str) -> dict[str, str]:
    """Response headers for serving a user-uploaded file of this type."""
    headers = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"}
    if mime != "application/pdf":
        headers["Content-Security-Policy"] = USER_FILE_CSP
    return headers


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
