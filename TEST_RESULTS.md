# Сборка публичного релиза StageOS 1.0.0

Коммит: 97a1966ce3033e03754318e413f5c5390d86969c
Проверки: https://github.com/wavessevaw/StageOS/actions/runs/37175900421

Обязательные задачи CI завершились успешно до создания этого отчёта:
- Linux: 112 backend-тестов; 19 основных UI-сценариев; 2 сценария пустой базы.
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
