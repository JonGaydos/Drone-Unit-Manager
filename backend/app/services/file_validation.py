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
