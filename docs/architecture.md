# Архитектура NCrew (MVP)

NCrew состоит из двух частей (frontend + backend) и использует файловую систему проекта, Git worktree и `opencode` CLI.

## Компоненты

```
┌────────────────────────────────────┐
│ Frontend (React + Vite)            │
│ - UI проектов/задач                │
│ - polling задач/логов              │
└───────────────┬────────────────────┘
                │ HTTP (/api)
┌───────────────▼────────────────────┐
│ Backend (Express)                  │
│ - проекты (config)                 │
│ - чтение задач из .memory_bank     │
│ - Git worktree                     │
│ - spawn/stop opencode              │
│ - логи + history                   │
└───────┬───────────────┬────────────┘
        │               │
        │ FS            │ Git / subprocess
        ▼               ▼
  ~/.ncrew/*        worktrees + opencode
  <project>/.memory_bank/*
```

## Хранилища

### Системные (глобальные)

```
~/.ncrew/
  settings/projects/*.json  # проекты
  settings/models-cache.json
  templates/*               # task/spec/plan
  stage_prompts/*           # prompts по стадиям
```

### В проекте

```
<project>/
  .memory_bank/tasks/*.md                 # задачи
  .memory_bank/tasks/<taskId>-history.json
  .memory_bank/logs/<taskId>-<stage>-<ts>.log
  worktrees/<prefix><taskId>/             # git worktree
```

## Основные потоки

### 1) Отображение задач

Frontend периодически вызывает `GET /api/projects/:id/tasks`, backend читает `.memory_bank/tasks/*.md`, добавляет `history` и список `logs`.

### 2) Запуск задачи

1. UI → `POST /api/tasks/:taskId/run`
2. Backend:
   - создаёт/переиспользует worktree
   - формирует prompt по текущему `stage` (из `~/.ncrew/stage_prompts`)
   - создаёт лог-файл и запись в history
   - запускает `opencode -m <provider>/<model> run <prompt>`
3. UI показывает статус `In Progress`, таймер и логи

### 3) Остановка

UI → `POST /api/tasks/:taskId/stop` → backend убивает процесс, обновляет status/history и дописывает лог.

