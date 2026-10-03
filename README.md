# StageOS

Локальное управление театральным производством: сотрудники, постановки, площадки, имущество, расчёт занятости и календарь.

Текущая ветка готовит **1.0.0-rc.1** с пустой рабочей базой. Руководство: [README_RU.md](README_RU.md). Результаты аудита и ограничения: [RELEASE_AUDIT_RU.md](RELEASE_AUDIT_RU.md). Это кандидат в релиз; непроверенный запуск Windows GUI не считается пройденной проверкой.

## Разработка

Python 3.12, Node 22+. `python -m venv .venv`, затем установите `requirements-lock.txt` в окружение. `npm ci --prefix frontend`, `npm run build --prefix frontend`. Запуск: `python -m backend.launcher` из активного окружения.

Обычный запуск создаёт пустую базу. Тестовые данные разрешаются только явным `STAGEOS_ENABLE_DEMO=1` при разработке и тестировании. Они не входят в Windows runtime рабочей сборки. Существующие пользовательские базы не удаляются.

Проверки: `python -m pytest tests -q`; из frontend — `npx playwright test` и `npx playwright test --config playwright.release.config.ts`. Рабочий сценарий с пустой базой выполняется отдельно от регрессии на тестовых фикстурах.

Windows Portable: `./build_windows.ps1 -Mode Portable` на Windows x64. GitHub Actions проверяет ядро, интерфейс, собирает Portable и проверяет встроенный runtime. Успешный импорт WinForms не заменяет ручную проверку окна на Windows 10/11.
