# Руководство для разработчиков NCrew

Этот документ описывает текущую (MVP) структуру репозитория и как локально разрабатывать NCrew.

## Структура репозитория

```
ncrew/
  backend/
    server.js
    utils/
      init.js
      migrate.js
      paths.js
  frontend/
    src/
    vite.config.js
  docs/
```

Ключевые места:
- Backend API + запуск `opencode`: `backend/server.js`
- Системные пути (`~/.ncrew/...`): `backend/utils/paths.js`
- Инициализация `~/.ncrew` (templates/stage_prompts): `backend/utils/init.js`
- Можно переопределить базовую директорию через `NCREW_HOME` (по умолчанию `~/.ncrew`)

## Запуск в development

```bash
npm run dev
```

- Frontend (Vite): `http://localhost:3000` (если порт занят — Vite выберет следующий)
- Backend (Express): по умолчанию `http://localhost:3001` (если порт занят — `npm run dev` выберет следующий свободный и прокинет его в Vite proxy `/api`)

Можно запускать отдельно:

```bash
npm run backend
npm run frontend
```

## Production (backend раздаёт `frontend/dist`)

```bash
npm -C frontend run build
node backend/server.js
```

Открыть: `http://localhost:3001`

## Как устроен MVP

- Проекты хранятся в `~/.ncrew/settings/projects/*.json`
- Шаблоны и промпты этапов: `~/.ncrew/templates/*` и `~/.ncrew/stage_prompts/*`
- Задачи читаются из `<project>/.memory_bank/tasks/*.md`
- История запусков: `<project>/.memory_bank/tasks/<taskId>-history.json`
- Логи запусков: `<project>/.memory_bank/logs/<taskId>-<stage>-<ts>.log`
- Worktree создаются в `<project>/worktrees/<prefix><taskId>`

Frontend использует polling списка задач и логов (без WebSocket) и отображает историю запусков (Timeline) в модалке задачи.

## E2E тесты (Playwright)

См. `docs/e2e-tests.md`.
