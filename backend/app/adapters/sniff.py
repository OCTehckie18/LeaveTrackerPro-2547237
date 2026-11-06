"""Trust the bytes, never the filename or the browser's Content-Type (docs/SECURITY.md section 7)."""

import io
import re
import unicodedata
import zipfile

PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_MAX_UNZIPPED = 30 * 1024 * 1024  # zip-bomb guard for DOCX
_MAX_ZIP_ENTRIES = 2000
INLINE_OK = frozenset({PDF, PNG, JPEG})
EXTENSIONS = {PDF: ".pdf", PNG: ".png", JPEG: ".jpg", DOCX: ".docx"}


def sniff_mime(data: bytes) -> str | None:
    """Return the real MIME type if it is on the allow-list, else None."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(b"PK\x03\x04"):
        return DOCX if _looks_like_docx(data) else None
    return None


def _looks_like_docx(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > _MAX_UNZIPPED:
                return False
            names = {i.filename for i in infos}
            return "[Content_Types].xml" in names and any(n.startswith("word/") for n in names)
    except zipfile.BadZipFile:
        return False


def sanitize_filename(raw: str | None, mime: str) -> str:
    """Display-only name: no path parts, no control characters, <= 120 chars, correct extension."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in unicodedata.normalize("NFC", name) if unicodedata.category(c) != "Cc")
    name = re.sub(r"\s+", " ", name).strip(" .")
    ext = EXTENSIONS[mime]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = stem.strip(" .") or "document"
    return stem[: 120 - len(ext)] + ext
