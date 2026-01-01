# NCrew - Agentic Harness

MVP для управления задачами и запуска AI-агентов в изолированных Git Worktree.

## Структура

```
ncrew/
├── backend/          # Express сервер (API)
├── frontend/         # React + Vite
└── docs/             # Документация
```

Системные настройки и шаблоны создаются автоматически в `~/.ncrew/`:

```
~/.ncrew/
  settings/
    projects/          # Конфиги проектов (JSON)
    models-cache.json  # Кеш моделей opencode
  templates/           # task.md / spec.md / plan.md
  stage_prompts/       # prompts для Specification/Plan/Implementation/Verification
```

Для каждого подключенного проекта NCrew использует:

```
<project_path>/
  .memory_bank/
    tasks/             # MD задачи (frontmatter)
    logs/              # Логи запусков (по файлам)
  worktrees/           # Git worktrees для задач
```

## Установка и запуск

1. Установить зависимости:
```bash
npm install
cd backend && npm install
cd ../frontend && npm install
```

2. Запустить в режиме разработки:
```bash
npm run dev
```

Frontend (Vite) поднимется на `http://localhost:3000` (если порт занят — выберет следующий).

Backend по умолчанию использует `http://localhost:3001`. Если порт занят, `npm run dev` автоматически выберет следующий свободный порт и настроит proxy `/api` в Vite.

3. Открыть в браузере: http://localhost:3000

Для “production” (backend раздаёт `frontend/dist`):
```bash
npm -C frontend run build
node backend/server.js
```
Открыть: http://localhost:3001

## Использование

1. Добавить проект через UI (укажите путь к проекту)
2. Создать задачи в папке `.memory_bank/tasks/` вашего проекта (MD-файлы с frontmatter)
3. Выбрать проект и нажать "Run" для запуска задачи

## Формат задач

Создайте MD-файл в `.memory_bank/tasks/`:

```markdown
---
title: Add authentication
stage: Specification
status: New
priority: High
---

Описание задачи...
```

Стадии: `Specification`, `Plan`, `Implementation`, `Verification`
Статусы: `New`, `In Progress`, `Done`, `Failed`
Приоритеты: `Low`, `Medium`, `High`
