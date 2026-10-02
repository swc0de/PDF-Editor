"""Exception types raised by the core layer.

Every exception carries a message that is safe to show to end users; the UI
layer turns these into friendly dialogs instead of tracebacks.
"""

from __future__ import annotations


class PdfEditorError(Exception):
    """Base class for all expected, user-facing errors."""

    title = "PDF Editor"

    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class PasswordRequired(PdfEditorError):
    """The document is encrypted and no password was supplied."""

    title = "Password required"


class WrongPassword(PdfEditorError):
    """The supplied password did not unlock the document."""

    title = "Wrong password"


class PermissionDenied(PdfEditorError):
    """The document's security settings do not allow the requested change."""

    title = "Not permitted"


class InvalidInput(PdfEditorError):
    """A parameter supplied by the user is not valid (page range, size, ...)."""

    title = "Invalid input"


class UnsupportedOperation(PdfEditorError):
    """The operation cannot be done reliably for this particular content."""

    title = "Not supported"


class OperationCancelled(PdfEditorError):
    """The user cancelled a long-running job."""

    title = "Cancelled"

    def __init__(self, message: str = "The operation was cancelled.") -> None:
        super().__init__(message)


class OcrUnavailable(PdfEditorError):
    """Tesseract OCR is not installed or cannot be located."""

    title = "OCR not available"


class JobFailed(PdfEditorError):
    """A background job raised an unexpected error."""

    title = "Operation failed"
