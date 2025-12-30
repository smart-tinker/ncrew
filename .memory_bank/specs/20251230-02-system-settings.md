---
title: System Settings (~/.ncrew)
stage: Plan
status: Done
priority: High
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
---

# Description

Перенести настройки из папки проекта в системную директорию `~/.ncrew` для возможности поставки в виде бинарника или контейнера.

## Requirements

### Структура ~/.ncrew

```
~/.ncrew/
  settings/
    projects/              # Конфиги проектов
    models-cache.json     # Кеш моделей
  templates/
    task.md              # Шаблон задачи
    spec.md              # Шаблон спецификации
    plan.md              # Шаблон плана
  stage_prompts/
    specification.md     # Промпт для этапа Specification
    plan.md              # Промпт для этапа Plan
    implementation.md    # Промпт для этапа Implementation
    verification.md      # Промпт для этапа Verification
```

### Структура проекта (логи)

```
<project_path>/
  .memory_bank/
    tasks/
      task-1.md
    logs/
      task-1-specification-1234567890.log
      task-1-plan-1234567891.log
      task-1-implementation-1234567892.log
    worktrees/                  # Git worktrees для задач
      task-1/
```

### Требования

1. Использовать `os.homedir()` для кроссплатформенности
2. Создать структуру папок при первом запуске
3. Перенести существующие настройки из `settings/` проекта
4. Обеспечить миграцию для существующих проектов
5. Логи задач хранить в проекте, а не в системных настройках

## Dependencies

- Зависит от: -
- Блокирует: Задача 2 (Шаблоны и промпты), Задача 3 (Воркфлоу), Задача 4 (Таймер и логи)

## Acceptance Criteria

- ✅ При запуске backend создаётся структура `~/.ncrew/`
- ✅ Существующие настройки мигрируются автоматически
- ✅ Пути вычисляются кроссплатформенно (Unix/macOS/Windows)
- ✅ API endpoints используют новые пути
- ✅ Логи сохраняются в `.memory_bank/logs/` проекта
