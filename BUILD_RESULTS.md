# Сборка StageOS 1.0.0-rc.1

Локальная среда: Linux x64. React/TypeScript production build — PASS. Новый Win32 launcher скомпилирован Zig 0.16.0 для Windows x64. Portable включает CPython 3.12.10 x64 и зафиксированные Windows wheels. Обновлённое приложение собрано с отключёнными примерами: seed.py и scenarios.py не входят в packaged backend.

- Статус native launcher: BUILT, PE32+ x64, subsystem Windows GUI.
- Статус Portable: ASSEMBLED; целостность ZIP и пустой базы проверяется упаковщиком.
- Windows runtime/WinForms/GUI в локальной Linux-среде: NOT TESTED.
- Tauri/NSIS: не собраны.
- Подпись EXE: отсутствует.

Workflow GitHub Actions выполняет сборку на Windows, проверку встроенного Python/SQLite/CP-SAT и импорт CLR/WinForms. Его наличие не считается успешным выполнением. После зелёного CI всё равно нужна приёмка окна и закрытия процесса на Windows 10/11.

## Подтверждённая Windows-сборка CI

GitHub Actions, Windows Server 2022 x64: [запуск 37163168708](https://github.com/wavessevaw/StageOS/actions/runs/37163168708), коммит 5967c802b00279f3f41fcd0b620a8533306257f9. Portable собран; 74 backend-теста, встроенный CPython 3.12.10, SQLite, CP-SAT и сохранение события — PASS. CLR/WinForms import — PASS. Ошибки конфликтующих pins, старого кэша wheels и незакрытого SQLite-пула самотеста исправлены. Окно Windows 10/11: NOT TESTED.

Публичная поставка собирается повторно релизным workflow; её собственный коммит и CI указаны в GITHUB_RELEASE_BUILD.md внутри ZIP.
