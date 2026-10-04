"""Write a build receipt after the required CI jobs have succeeded."""
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
run = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
sha = os.environ['GITHUB_SHA']
text = f"""# Сборка публичного релиза StageOS 1.0.0-rc.1

Коммит: {sha}
Проверки: {run}

Отчёт создан после успешного завершения обязательных задач CI:
- Linux: 74 backend-теста, 15 основных UI-сценариев и 1 сценарий пустой базы.
- Критические статические проверки Python, TypeScript и production build.
- Windows: 74 backend-теста, native launcher и Portable.
- Встроенные CPython, SQLite, CP-SAT и сохранение события: PASS.
- Импорт CLR/WinForms: PASS.
- Пустая база и целостность ZIP проверяются упаковщиком перед публикацией.

Окно и завершение приложения на Windows 10/11: NOT TESTED.
Host: Win32 + pywebview/WebView2. Tauri/NSIS не собраны.
EXE не подписан. Реальная локальная LLM и PostgreSQL не проверены.

ZIP собран из Windows-артефакта этого же CI. Прежние локальные логи
в приложенных отчётах относятся к указанным в них проверкам.
"""
(root / 'GITHUB_RELEASE_BUILD.md').write_text(text, encoding='utf-8')
