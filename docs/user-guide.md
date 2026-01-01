# Руководство пользователя NCrew

NCrew помогает управлять задачами (MD-файлы) и запускать `opencode` в изолированных Git worktree, сохраняя логи и историю запусков.

## Добавление проекта

1. Откройте UI:
   - dev: `http://localhost:3000`
   - prod: `http://localhost:3001`
2. Нажмите “Add Project”
3. Заполните поля:
   - **Name** — имя проекта (используется как `id`)
   - **Path** — абсолютный путь к репозиторию
   - **Worktree Prefix** — префикс для worktree (например `task-` или `wt-`)
   - **Default Model** — модель по умолчанию (можно переопределять на уровне задач)

Проект хранится в `~/.ncrew/settings/projects/<projectId>.json`.

## Формат задач

Задачи — это файлы в `<project>/.memory_bank/tasks/*.md`.

Минимальный пример:

```markdown
---
title: My task
stage: Specification
status: New
priority: Medium
---

# Description

...
```

### Поля

- `title` — заголовок задачи
- `stage` — этап: `Specification`, `Plan`, `Implementation`, `Verification`
- `status` — статус: `New`, `In Progress`, `Done`, `Failed`
- `priority` — приоритет: `Low`, `Medium`, `High`
- `modelProvider` / `modelName` — модель для запуска (опционально; иначе берётся defaultModel проекта)

## Запуск задачи

1. Откройте страницу проекта
2. Нажмите “Run” у нужной задачи
3. Выберите модель (если нужно) и подтвердите запуск

Во время выполнения:
- статус меняется на `In Progress`
- появляется таймер
- доступна кнопка “Stop”

## Логи и история запусков

NCrew сохраняет:
- логи: `<project>/.memory_bank/logs/<taskId>-<stage>-<timestamp>.log`
- историю запусков: `<project>/.memory_bank/tasks/<taskId>-history.json`

В модалке задачи:
- **Timeline** показывает запуски (стадия, статус, время, длительность, лог-файл)
- **Logs** позволяет открыть конкретный лог (группировка по стадиям)

## Стадии (Workflow)

Кнопка “Next Stage” появляется, если:
- `status: Done`
- текущая стадия не `Verification`

Нажатие:
- переводит `stage` на следующий этап
- сбрасывает `status` на `New`

## Worktree

При запуске задачи NCrew создаёт/использует worktree:

```
<project>/worktrees/<prefix><taskId>/
```

Изменение `worktreePrefix` через “Edit” проекта не влияет на уже созданные worktree (они остаются на диске).

