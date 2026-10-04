"""Fetch pinned Windows runtime artifacts for a reproducible portable assembly."""

from pathlib import Path
import subprocess, sys, urllib.request, zipfile, hashlib

ROOT = Path(__file__).resolve().parent.parent
DOWNLOADS = ROOT / "windows-build/downloads"
WHEELS = ROOT / "windows-build/wheels"
DOWNLOADS.mkdir(parents=True, exist_ok=True)
WHEELS.mkdir(parents=True, exist_ok=True)
url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
pythonzip = DOWNLOADS / "python-3.12.10-embed-amd64.zip"
if not pythonzip.exists():
    urllib.request.urlretrieve(url, pythonzip)
with zipfile.ZipFile(pythonzip) as z:
    if z.testzip() is not None:
        raise RuntimeError("CPython download is damaged")
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "download",
        "--dest",
        str(WHEELS),
        "--platform",
        "win_amd64",
        "--python-version",
        "312",
        "--implementation",
        "cp",
        "--abi",
        "cp312",
        "--only-binary=:all:",
        "--no-deps",
        "-r",
        str(ROOT / "windows-runtime-lock.txt"),
    ],
    check=True,
)
subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--wheel-dir",
        str(WHEELS),
        "proxy_tools==0.1.0",
    ],
    check=True,
)
print("Windows wheels ready:", len(list(WHEELS.glob("*.whl"))))
