# NCrew - Agentic Harness

MVP для управления задачами и запуска AI-агентов в изолированных Git Worktree.

## Структура

```
ncrew/
├── backend/          # Express сервер (API)
├── frontend/         # React + Vite
└── settings/         # Настройки проектов (создается автоматически)
    └── projects/     # Конфиги проектов (JSON)
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

Backend запустится на порту 3001, Frontend - на порту 3000.

3. Открыть в браузере: http://localhost:3000

## Использование

1. Добавить проект через UI (укажите путь к проекту)
2. Создать задачи в папке `.memory_bank/tasks/` вашего проекта (MD-файлы с frontmatter)
3. Выбрать проект и нажать "Run" для запуска задачи

## Формат задач

Создайте MD-файл в `.memory_bank/tasks/`:

```markdown
---
title: Add authentication
status: New
priority: High
---

Описание задачи...
```

Статусы: `New`, `In Progress`, `Done`, `Failed`
Приоритеты: `Low`, `Medium`, `High`
