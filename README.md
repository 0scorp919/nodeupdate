# Node.js Portable Manager v1.5

Менеджер автооновлення та запуску Node.js Portable у Autonomous Capsule.

## Запуск

```
Win+R → node
```

Або напряму:

```
tags\node.bat
```

Або GitHub-ready лаунчер (без хардкодованих шляхів):

```
devops\nodeupdate\node_launcher.bat
```

## Алгоритм роботи

1. **Перевірка PATH** — `apps/node/` у HKLM PATH, UAC → `fix_path.ps1 -AutoClose` якщо відсутній
2. **Очищення логів** — видалення файлів старших за 7 днів з `logs/nodelog/` (поточний день захищений)
3. **Перевірка інструментів** — `node --version`, `npm --version`, `npx --version`, список глобальних пакетів
4. **Оновлення глобальних пакетів** — `npm outdated -g` → `npm update -g` (виконується завжди)
5. **Перевірка оновлення** — GitHub Releases API (`nodejs/node`), LTS-реліз (парна мажорна версія)
6. **Оновлення** (якщо знайдено нову версію):
   - Збереження `node_modules/` (глобальні пакети)
   - Завантаження `node-v{ver}-win-x64.zip` з GitHub Releases або nodejs.org
   - Розпакування через `zipfile` (без зовнішніх залежностей)
   - Копіювання файлів у `apps/node/`
   - Відновлення `node_modules/`
   - `npm rebuild` — перекомпіляція нативних `.node` бінарників
7. **Запуск PowerShell** — `apps/pwsh/pwsh.exe` з `NODE_DIR` у PATH та робочою директорією `apps/node/`

## Портативність

`CAPSULE_ROOT` визначається автоматично від розташування скрипту:

```
SCRIPT_DIR   = dirname(abspath(__file__))          # .../devops/nodeupdate/
CAPSULE_ROOT = abspath(SCRIPT_DIR + "/../..")      # .../  (корінь капсули)
```

Структура шляхів:
- `CAPSULE_ROOT/apps/node/` — Node.js runtime
- `CAPSULE_ROOT/logs/nodelog/` — логи
- `CAPSULE_ROOT/downloads/` — тимчасові завантаження
- `CAPSULE_ROOT/apps/pwsh/pwsh.exe` — PowerShell
- `CAPSULE_ROOT/devops/pathupdate/fix_path.ps1` — реєстрація PATH

Хардкод шляхів відсутній — проект працює з будь-якого розташування капсули.

## Портативний лаунчер (GitHub-ready)

`node_launcher.bat` — лаунчер для публікації проекту на GitHub:
- Auto-detect `CAPSULE_ROOT` від `%~dp0` (два рівні вгору: `nodeupdate\` → `devops\` → `CAPSULE_ROOT\`)
- Без хардкодованих шляхів — працює з будь-якого розташування capsule
- UAC elevation, перевірки безпеки (Python + скрипт), передача `%*` аргументів
- Виводить `Capsule: %CAPSULE_ROOT%` для підтвердження auto-detect

Відмінність від `tags/node.bat`:
- `tags/node.bat` — системний лаунчер, може містити хардкод, не публікується
- `node_launcher.bat` — GitHub-ready, лежить поруч з менеджером, повністю портативний

## Структура файлів

```
devops/nodeupdate/
  node_manager.py     — головний менеджер (v1.5)
  node_launcher.bat   — портативний лаунчер (GitHub-ready, auto-detect від %~dp0)
  .env.example        — шаблон змінних середовища (пояснення чому .env не потрібен)
  .gitignore          — мінімальний стандарт капсули
  README.md           — ця документація

tags/
  node.bat            — системний лаунчер (UAC elevation → node_manager.py)

logs/nodelog/
  node_log_YYYY-MM-DD.log         — щоденні логи (ротація 7 днів)
  node_log_YYYY-MM-DD_part2.log   — якщо лог перевищив 50 MB

apps/node/
  node.exe          — Node.js runtime
  npm.cmd           — npm package manager
  npx.cmd           — npx runner
  node_modules/     — глобальні пакети (зберігаються при оновленні)
```

## Стратегія оновлення

- Джерело: GitHub Releases API `https://api.github.com/repos/nodejs/node/releases`
- Тип: LTS-реліз (парна мажорна версія: 18, 20, 22, 24...)
- Asset: `node-v{ver}-win-x64.zip`
- Fallback: `https://nodejs.org/dist/v{ver}/node-v{ver}-win-x64.zip`
- Порівняння: `packaging.version.Version` (семантичне версіонування)
- Збереження: `node_modules/` зберігається при оновленні (глобальні пакети не втрачаються)

## Оновлення глобальних пакетів

Виконується при **кожному** запуску, незалежно від оновлення Node.js:

- `npm outdated -g --json` → список застарілих пакетів з версіями `current → latest`
- Замість `npm update -g` — окремі `npm install -g <pkg>@latest` для кожного застарілого пакету (фікс Windows-багу ENOTEMPTY)
- Windows-specific баг: `npm update -g` на Windows викидав попередження `npm warn cleanup Failed to remove some directories` з помилкою `ENOTEMPTY: directory not empty, rmdir '...\node_modules\cline\node_modules\date-fns\locale\de-AT'`
- Рішення: для кожного застарілого пакету окремий виклик `npm install -g <pkg>@latest` з timeout 120 секунд
- Обробка warning-ів: якщо `npm install -g` повертає помилку з "ENOTEMPTY", вважаємо це лише warning cleanup та логуємо як успішне оновлення
- RC=1 від `npm outdated` обробляється коректно (нормальна поведінка при наявності застарілих пакетів)
- Якщо всі пакети актуальні → `✅ Всі глобальні пакети актуальні.`

## Залежності

Python-бібліотеки (self-healing pip install):
- `requests` — HTTP-запити до GitHub API та завантаження
- `packaging` — порівняння семантичних версій

Системні (вже є в капсулі):
- `apps/python/current/` — Python runtime (WinPython Portable)
- `apps/pwsh/pwsh.exe` — PowerShell для запуску
- `devops/pathupdate/fix_path.ps1` — реєстрація PATH

## Логи

- Розташування: `logs/nodelog/node_log_YYYY-MM-DD.log`
- Ротація: 7 днів за датою (поточний день ніколи не видаляється)
- При >50 MB: активний лог перейменовується у `_part2`, `_part3`... (новий файл продовжує запис)
- Формат: `YYYY-MM-DD HH:MM:SS [INFO] повідомлення`

## Чому немає резервних копій

Node.js — CLI-інструмент без даних користувача:
- Бінарники відновлюються з GitHub Releases (nodejs/node)
- `node_modules/` (глобальні пакети) відновлюються через `npm install -g`
- Немає конфігурацій, профілів або сесій користувача

Аналогічний підхід: `7zip_manager.py`, `git_manager.py`.

## Troubleshooting

**node.exe не знайдено:**
- Перевір: `apps/node/node.exe` існує
- Перевстанови Node.js Portable вручну з `https://nodejs.org/dist/`

**npm/npx не відповідають:**
- Перевір: `apps/node/npm.cmd`, `apps/node/npx.cmd` існують
- Запусти `Win+R → node` — менеджер перевірить та виправить PATH

**Оновлення не вдалося:**
- Перевір інтернет-з'єднання
- GitHub API rate limit: 60 запитів/год без токена
- Fallback: завантаж вручну з `https://nodejs.org/dist/latest/`

**npm update -g зависає:**
- Timeout: 5 хвилин (300 сек) — достатньо для більшості пакетів
- Перевір інтернет-з'єднання та npm registry доступність

**PowerShell не запускається:**
- Перевір: `apps/pwsh/pwsh.exe` існує
- Fallback: менеджер використає системний `pwsh`

**PATH не оновлюється:**
- Запусти `Win+R → node` з правами адміністратора (UAC)
- Або вручну: `devops/pathupdate/fix_path.ps1`

**CAPSULE_ROOT визначається неправильно:**
- Перевір структуру: `node_manager.py` має бути у `<CAPSULE_ROOT>/devops/nodeupdate/`
- `SCRIPT_DIR/../..` має вказувати на корінь капсули
- Запусти `node_launcher.bat` — він виводить `Capsule: <path>` для підтвердження

## CHANGELOG

- **v1.5** — Виправлено Windows-специфічний npm баг ENOTEMPTY при cleanup вкладених node_modules:
  - Проблема: `npm update -g` на Windows викидав попередження `npm warn cleanup Failed to remove some directories` з помилкою `ENOTEMPTY: directory not empty, rmdir '...\node_modules\cline\node_modules\date-fns\locale\de-AT'`
  - Діагноз: npm на Windows не може видалити непусті вкладені `node_modules` під час cleanup старих файлів, хоча оновлення фактично відбувається успішно
  - Рішення: замінено `npm update -g` на окремі `npm install -g <pkg>@latest` для кожного застарілого пакету
  - Обробка warning-ів: якщо `npm install -g` повертає помилку з "ENOTEMPTY", вважаємо це лише warning cleanup та логуємо як успішне оновлення
  - Логіка: для кожного застарілого пакету окремий виклик `npm install -g <pkg>@latest` з timeout 120 секунд
  - Результат: оновлення проходить без ENOTEMPTY помилок, Windows-specific баг обійдено
- **v1.4** — Підготовка до публікації на GitHub (стандарт capsule_manager): `CAPSULE_ROOT` auto-detect від `SCRIPT_DIR`, `__version__ = "1.4"` + `get_manager_hash()`, `_rotate_log_if_needed()` (>50 MB → part-файл), `cleanup_old_logs()` за датою з захистом поточного дня. Додано: `node_launcher.bat`, `.gitignore`, `.env.example`.
- **v1.3** — Видалено резервне копіювання та Vaultwarden-стек (Node = CLI-інструмент без даних користувача, як `7zip_manager`). Спрощено `main()` до 6 кроків.
- **v1.2** — Додано `update_global_packages()` — оновлення глобальних npm-пакетів при кожному запуску
- **v1.1** — Додано Vaultwarden-стек, резервне копіювання `apps/node/` (AES-256), ротація 7+4
- **v1.0** — Початкова версія: перевірка версії, LTS-оновлення, збереження `node_modules/`, `npm rebuild`, `ensure_in_system_path()`
