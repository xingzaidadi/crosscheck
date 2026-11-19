import hashlib
from pathlib import Path

from core.ui_actions import replay


class Download:
    suggested_filename = "result.txt"

    def save_as(self, path):
        Path(path).write_text("hello", encoding="utf-8")


class DownloadContext:
    value = Download()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Locator:
    @property
    def first(self):
        return self

    def set_input_files(self, path, timeout=0):
        assert Path(path).is_file()

    def click(self, timeout=0):
        return None

    def count(self):
        return 1

    def wait_for(self, state="visible", timeout=0):
        return None


class Page:
    def locator(self, _selector):
        return Locator()

    def expect_download(self, timeout=0):
        return DownloadContext()

    def get_by_text(self, _text, exact=False):
        return Locator()


def test_upload_and_download_actions_capture_file_evidence(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    result = replay(Page(), [
        {"action": "upload", "selector": "input", "path": str(source)},
        {"action": "download", "text": "下载", "output_dir": str(tmp_path),
         "expected_name": "result.txt", "sha256": hashlib.sha256(b"hello").hexdigest()},
    ])
    assert all(item["ok"] for item in result)
    assert result[1]["size"] == 5
