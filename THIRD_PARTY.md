# Third-party dependencies

StageOS uses React, Vite, FullCalendar core/daygrid/timegrid/interaction, Lucide, FastAPI, SQLAlchemy, Alembic, Pydantic, Uvicorn and Google OR-Tools. FullCalendar premium modules are not included; Production View is implemented in the application. Tauri source is included as an alternative desktop host.

Windows Portable includes official CPython 3.12.10 embedded, pywebview, pythonnet, clr_loader, and pinned Windows Python dependencies. Their distribution license files and dist-info metadata are preserved in runtime/Lib/site-packages; CPython LICENSE.txt is in runtime. WINDOWS_RUNTIME_MANIFEST.json records wheel versions and hashes. NumPy's redistributed MSVC runtime DLL is also copied under its standard import name; NumPy's license notices remain included.

The native launcher was compiled with Zig 0.16.0; the Zig toolchain itself is not shipped. Microsoft Edge WebView2 Runtime and .NET Framework are external prerequisites. No test Chromium, Wine, node_modules, or developer virtual environment is shipped. The bundled frontend contains the production React build.

Retain upstream license notices when redistributing this package. Lock files provide exact dependency versions; upstream projects remain responsible for their own license terms.

## Schedule export

ReportLab (BSD license), Pillow (HPND license) and DejaVu Sans fonts are used for offline PDF/PNG export. Font license and bundled files: `backend/assets/fonts/LICENSE.txt`. Fonts are embedded in PDFs so Cyrillic text does not depend on fonts installed on the user's computer.
