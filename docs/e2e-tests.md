# E2E тесты (Playwright, без AI)

В репозитории есть полноценные e2e-тесты на Playwright, которые проверяют основной UI‑путь NCrew **без запуска реального `opencode`/AI** (используется фейковый бинарник).

## Что покрыто

- Главная страница Projects
- `Refresh Models` (alert “Models refreshed successfully”)
- Добавление проекта через UI
- Список задач проекта
- Запуск задачи (Run modal → In Progress → логи/таймлайн → Done)
- Проверка, что в prompt/log используются шаблоны из worktree: `.ncrew/templates/*.md` (а не `~/.ncrew/templates/*`)
- `Edit Project`: предупреждение (confirm) при смене `worktreePrefix`, если уже есть worktree со старым префиксом
- `Next Stage` (смена стадии + сброс статуса на `New`)
- `Stop` (остановка долгого запуска → `Failed`)
- Отсутствие `Next Stage` на стадии `Verification`

## Как запустить

1. Установить зависимости:
```bash
npm install
npm -C backend install
npm -C frontend install
```

2. Установить браузер для Playwright (один раз на машину/CI):
```bash
npx playwright install --with-deps chromium
```

3. Запустить e2e:
```bash
npm run test:e2e
```

## Как это работает (без AI)

- Фейковый `opencode` лежит в `tests/e2e/bin/opencode`.
  - Он поддерживает команды `opencode models` и `opencode -m <model> run <prompt>`.
  - Специально читает stdin до EOF — это ловит регресс, когда NCrew спавнит `opencode` с “висящим” stdin.
- Раннер `scripts/e2e.js`:
  - создаёт временный git‑проект в `.tmp/e2e/project` с фикстурными задачами,
  - стартует backend на свободном порту,
  - изолирует системные настройки NCrew через `NCREW_HOME=.tmp/e2e/ncrew-home`,
  - прогоняет `npx playwright test -c playwright.e2e.config.js`.

## Полезные переменные окружения

- `E2E_MODEL_FULL_NAME=opencode/glm-4.7-free` — модель, которая используется в fixture‑задачах и выбирается по умолчанию в Run modal (можно заменить на другую “бесплатную” модель).
- `E2E_HEADED=1` — запуск браузера в headed‑режиме:
  - `E2E_HEADED=1 npm run test:e2e`
- `E2E_KEEP_TMP=1` — не удалять `.tmp/e2e` после прогона (для дебага артефактов).
- `E2E_PORT=4300` — стартовый порт (скрипт выберет первый свободный в диапазоне).
