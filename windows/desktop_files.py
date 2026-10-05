"""Save exported bytes on the client computer using a native save dialog."""
import base64
import os
from pathlib import Path
import tempfile

MAX_BYTES = 64 * 1024 * 1024
SIGNATURES = {".pdf": b"%PDF-", ".png": b"\x89PNG\r\n\x1a\n", ".zip": b"PK\x03\x04", ".db": b"SQLite format 3\0"}


class DesktopFiles:
    def __init__(self, origin):
        self._origin = origin.rstrip("/") + "/"
        self._window = None

    def save_file(self, filename, encoded):
        try:
            if self._window is None or not self._window.get_current_url().startswith(self._origin):
                raise ValueError("Недоступно из этого окна")
            if not isinstance(filename, str) or any(x in filename for x in ('/', '\\', ':')):
                raise ValueError("Некорректное имя файла")
            extension = Path(filename).suffix.lower()
            if extension not in SIGNATURES:
                raise ValueError("Неподдерживаемый формат файла")
            if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
                raise ValueError("Файл слишком большой для сохранения в окне приложения")
            data = base64.b64decode(encoded, validate=True)
            if len(data) > MAX_BYTES or not data.startswith(SIGNATURES[extension]):
                raise ValueError("Некорректное содержимое файла")
            import webview
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE, save_filename=filename,
                file_types=(f"StageOS (*{extension})",),
            )
            if not selected:
                return {"status": "cancelled"}
            target = Path(selected if isinstance(selected, str) else selected[0])
            if not target.suffix:
                target = target.with_suffix(extension)
            if target.suffix.lower() != extension:
                raise ValueError("Сохраните файл с расширением " + extension)
            # Do not truncate an existing export if a write fails.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(data)
                os.replace(temporary, target)
            finally:
                if temporary and temporary.exists():
                    temporary.unlink()
            return {"status": "saved", "path": str(target)}
        except Exception as error:
            return {"status": "error", "message": str(error)}
