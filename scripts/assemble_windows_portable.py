"""Assemble official CPython embed + pinned Windows wheels; no host Python required."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from packaging.utils import parse_wheel_filename
import shutil, json, hashlib

ROOT = Path(__file__).resolve().parent.parent
WHEELS = ROOT / "windows-build/wheels"
OUT = ROOT / "artifacts/StageOS-Portable"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)
runtime = OUT / "runtime"
runtime.mkdir(exist_ok=True)
with ZipFile(ROOT / "windows-build/downloads/python-3.12.10-embed-amd64.zip") as z:
    z.extractall(runtime)
site = runtime / "Lib/site-packages"
site.mkdir(parents=True, exist_ok=True)
manifest = []
# Select only locked versions: an old download cache must not overwrite packages.
pins = {}
for line in (ROOT / "windows-runtime-lock.txt").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    name, version = line.split("==")
    key = name.lower().replace("_", "-")
    if key in pins:
        raise ValueError(f"Duplicate runtime pin: {name}")
    pins[key] = version
pins["proxy-tools"] = "0.1.0"
selected = {}
for wheel in sorted(WHEELS.glob("*.whl")):
    name, version, _, _ = parse_wheel_filename(wheel.name)
    key = str(name).replace("_", "-")
    if pins.get(key) == str(version):
        if key in selected:
            raise ValueError(f"Multiple runtime wheels: {key}")
        selected[key] = wheel
missing = pins.keys() - selected.keys()
if missing:
    raise ValueError(f"Missing runtime wheels: {sorted(missing)}")
for wheel in selected.values():
    with ZipFile(wheel) as z:
        for name in z.namelist():
            parts = Path(name).parts
            if ".." in parts or name.startswith("/"):
                raise ValueError("Unsafe wheel path")
            if ".data/" in name:
                prefix, suffix = name.split(".data/", 1)
                scheme, _, remaining = suffix.partition("/")
                if scheme not in ["purelib", "platlib"]:
                    continue
                dest = site / remaining
            else:
                dest = site / name
            if name.endswith("/"):
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
    name, version, _, _ = parse_wheel_filename(wheel.name)
    manifest.append(
        {
            "package": str(name),
            "version": str(version),
            "wheel": wheel.name,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        }
    )
# NumPy's wheel redistributes the MSVC runtime; preserve its license and reuse the DLL under its standard import name.
crt = next((site / "numpy.libs").glob("msvcp140-*.dll"))
shutil.copyfile(crt, runtime / "msvcp140.dll")
(runtime / "python312._pth").write_text(
    "python312.zip\n.\nLib/site-packages\n../app\nimport site\n"
)
app = OUT / "app"
app.mkdir(exist_ok=True)
for folder in ["backend", "migrations"]:
    shutil.copytree(
        ROOT / folder,
        app / folder,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "seed.py", "scenarios.py"),
    )
shutil.copytree(ROOT / "frontend/dist", app / "frontend/dist", dirs_exist_ok=True)
shutil.copyfile(ROOT / "windows/windows_desktop.py", app / "windows_desktop.py")
shutil.copyfile(ROOT / "windows/StageOS.exe", OUT / "StageOS.exe")
shutil.copyfile(ROOT / "windows/StageOS.exe", OUT / "StageOS Server.exe")
shutil.copyfile(ROOT / "windows/StageOS.ico", OUT / "StageOS.ico")
(OUT / "WINDOWS_RUNTIME_MANIFEST.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
)
(OUT / "START_HERE_RU.txt").write_text(
    "StageOS 1.0.4\n\n1. Распакуйте всю папку в любое место.\n2. Запустите StageOS.exe двойным щелчком.\n3. Для общей базы на главном ПК откройте StageOS Server.exe; на остальных — StageOS.exe.\n4. Инструкция: docs/SERVER_SETUP_RU.md в основном архиве.\n5. Выберите театр или создайте свой.\n6. Войдите по логину и паролю.\n\nPython, сервер базы и терминал запускать не нужно.\nДля окна требуется Microsoft Edge WebView2 Runtime (обычно уже установлен в Windows 11).\nДанные: %LOCALAPPDATA%\\StageOS-Work. Ошибки старта: startup-error.log в том же каталоге.\n\nWindows runtime включён. Сборка и запуск окна проверяются на Windows Server 2022 в GitHub Actions. Ручная проверка на Windows 10/11 не выполнена. Перед распаковкой скачанного ZIP снимите блокировку в его свойствах, если она есть.\n",
    encoding="utf-8",
)
print(OUT)
