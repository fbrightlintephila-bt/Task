from pathlib import Path
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document

ALLOWED_EXTENSIONS = {".py", ".txt", ".pdf", ".docx", ".md"}


class UploadError(ValueError):
    pass


def extract_submission(upload, upload_folder, max_bytes):
    if not upload or not upload.filename:
        return "", None, None
    safe_name = secure_filename(upload.filename)
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in ALLOWED_EXTENSIONS:
        raise UploadError("Unsupported file. Allowed formats: .py, .txt, .pdf, .docx, .md.")
    data = upload.stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise UploadError("The uploaded file exceeds the assignment size limit.")
    if not data:
        raise UploadError("The uploaded file is empty.")
    upload.stream.seek(0)
    folder = Path(upload_folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    import uuid
    target = folder / f"{uuid.uuid4().hex}{suffix}"
    target.write_bytes(data)
    try:
        if suffix in {".py", ".txt", ".md"}:
            text = data.decode("utf-8-sig")
        elif suffix == ".docx":
            text = "\n".join(paragraph.text for paragraph in Document(target).paragraphs)
        else:
            reader = PdfReader(str(target))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if not text:
                raise UploadError("No selectable text was found in the PDF. OCR is required for scanned documents.")
    except UnicodeDecodeError as exc:
        target.unlink(missing_ok=True)
        raise UploadError("Text files must use UTF-8 encoding.") from exc
    except Exception as exc:
        target.unlink(missing_ok=True)
        if isinstance(exc, UploadError):
            raise
        raise UploadError("The file could not be read as a valid supported document.") from exc
    if not text.strip():
        target.unlink(missing_ok=True)
        raise UploadError("No readable text was found in the uploaded file.")
    return text, str(target), safe_name
