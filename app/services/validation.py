"""File validation (Sections 8, 51): extension, size, and magic-byte signature checks."""

from pathlib import Path

from app.core.config import settings

# Leading magic bytes for the formats we accept. Text formats have no reliable
# signature, so they're validated by extension + decodability instead.
_SIGNATURES = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # docx is a zip container
}


class ValidationError(Exception):
    pass


def validate_upload(filename: str, data: bytes) -> str:
    """Validate an uploaded file. Returns the normalized extension or raises."""
    ext = Path(filename).suffix.lower()

    if ext not in settings.ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"Unsupported file type '{ext}'. Allowed: "
            f"{', '.join(sorted(settings.ALLOWED_EXTENSIONS))}"
        )

    if not data:
        raise ValidationError("The uploaded file is empty.")

    max_bytes = settings.UPLOAD_MAX_SIZE_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise ValidationError(
            f"File is too large ({len(data) / 1_048_576:.1f} MB). "
            f"Limit is {settings.UPLOAD_MAX_SIZE_MB} MB."
        )

    expected = _SIGNATURES.get(ext)
    if expected and not any(data.startswith(sig) for sig in expected):
        raise ValidationError(
            f"File content does not match a valid {ext} file (signature check failed)."
        )

    if ext in {".txt", ".md", ".markdown"}:
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationError("Text file is not valid UTF-8.")

    return ext
