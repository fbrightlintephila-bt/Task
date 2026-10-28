import io
import pytest
from submission_utils import UploadError, extract_submission


def test_supported_text_upload_is_safely_named_and_extracted(tmp_path):
    from werkzeug.datastructures import FileStorage
    uploaded = FileStorage(stream=io.BytesIO(b"print('hello')"), filename="../../unsafe name.py")
    text, path, original = extract_submission(uploaded, tmp_path, 1000)
    assert text == "print('hello')"
    assert original == "unsafe_name.py"
    assert path.startswith(str(tmp_path.resolve()))
    assert open(path, encoding="utf-8").read() == text


@pytest.mark.parametrize("filename,data", [("evil.exe", b"data"), ("empty.txt", b"")])
def test_rejects_unsupported_and_empty_uploads(tmp_path, filename, data):
    from werkzeug.datastructures import FileStorage
    with pytest.raises(UploadError):
        extract_submission(FileStorage(stream=io.BytesIO(data), filename=filename), tmp_path, 1000)


def test_rejects_oversized_upload(tmp_path):
    from werkzeug.datastructures import FileStorage
    with pytest.raises(UploadError):
        extract_submission(FileStorage(stream=io.BytesIO(b"12345"), filename="a.txt"), tmp_path, 4)
