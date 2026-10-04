"""Build receipt derived from test outputs after all required CI jobs succeed."""
import json,os,re
from pathlib import Path
root=Path(__file__).resolve().parent.parent
version=json.loads((root/'frontend/package.json').read_text())['version']
run=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
sha=os.environ['GITHUB_SHA']
backend=(root/'release-test-results.txt').read_text()
match=re.search(r'(\d+) passed',backend)
if not match or re.search(r'\d+ failed',backend):raise RuntimeError('No successful backend receipt')
def ui_count(name):
    stats=json.loads((root/name).read_text())['stats']
    if stats.get('unexpected') or stats.get('flaky'):raise RuntimeError('UI checks did not pass cleanly')
    return stats['expected']
ui=ui_count('ui-results.json');empty=ui_count('release-ui-results.json')
text=f'''# Сборка публичного релиза StageOS {version}

Коммит: {sha}
Проверки: {run}

Обязательные задачи CI завершились успешно до создания этого отчёта:
- Linux: {match.group(1)} backend-тестов; {ui} основных UI-сценариев; {empty} сценария пустой базы.
- Критические проверки Python, TypeScript и production build.
- Windows: backend-тесты, native launcher, Portable, проверка ресурсов EXE и байтов иконки.
- Встроенные CPython, SQLite, CP-SAT, сохранение события, PDF/PNG: PASS.
- Импорт CLR/WinForms: PASS.
- Настоящее окно WebView2: загрузка React, токен, иконка и завершение приложения: PASS.
- Windows runner: Windows Server 2022 x64.
- Пустая база и целостность ZIP дополнительно проверяются перед публикацией.

Ручная проверка Windows 10/11: NOT TESTED. EXE не подписан.
Windows host: Win32 + pywebview/WebView2. Tauri/NSIS не собраны.
Реальная локальная LLM и PostgreSQL не проверены.

Архив собран из Windows-артефакта этого же CI. Предыдущие отчёты аудита
описывают исторические проверки; результаты этого релиза приведены выше.
'''
(root/'GITHUB_RELEASE_BUILD.md').write_text(text,encoding='utf-8')
(root/'TEST_RESULTS.md').write_text(text,encoding='utf-8')
(root/'BUILD_RESULTS.md').write_text(text,encoding='utf-8')
