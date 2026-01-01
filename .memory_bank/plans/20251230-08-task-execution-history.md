# План реализации: Task Execution History

**Основан на спецификации:** `.memory_bank/specs/20251230-08-task-execution-history.md`  
**Дата:** 2025-12-30  
**Версия:** 1.1

## Обзор

Добавить историю запусков задач (по стадиям) и отображение этой истории в UI, чтобы можно было:
- видеть все запуски (когда/чем/какой стадией),
- быстро открыть лог нужного запуска,
- понимать длительность выполнения и модель.

## Предварительные требования

1. Задачи читаются из `<project>/.memory_bank/tasks/*.md`
2. Логи пишутся в `<project>/.memory_bank/logs/*.log`
3. Стадия задачи хранится в frontmatter (`stage`)

## Этап 1: Backend — история в `<taskId>-history.json`

### 1.1. Формат хранения

**Путь:** `<project>/.memory_bank/tasks/<taskId>-history.json`

**Формат:**
```json
{ "history": [] }
```

**Элемент history:**
- `id`: `run-<timestamp>`
- `stage`: `Specification|Plan|Implementation|Verification`
- `status`: `In Progress|Done|Failed`
- `startedAt`, `completedAt`, `duration`
- `model`: `{ agenticHarness, modelProvider, modelName, fullName }`
- `logFile`: имя файла лога (без пути)

### 1.2. Функции для работы с историей

**Файл:** `backend/server.js`

- `readTaskHistory(tasksDir, taskId)` — вернуть `{ history: [] }` (если файла нет/битый)
- `appendHistoryEntry(tasksDir, taskId, entry)` — добавить запись и сохранить
- `updateHistoryEntry(tasksDir, taskId, runId, updates)` — найти запись по `id` и обновить

### 1.3. Запись истории при запуске/завершении

**Файл:** `backend/server.js`

При `POST /api/tasks/:taskId/run`:
- создать `runId`, `logFile`
- обновить task frontmatter: `status: In Progress`, `startedAt`
- `appendHistoryEntry(..., { id, stage, status: 'In Progress', startedAt, model, logFile })`

При завершении (`close`) или остановке (`stop`):
- вычислить `completedAt`, `duration`
- `updateHistoryEntry(..., { status: 'Done'|'Failed', completedAt, duration })`
- обновить task frontmatter `status`

## Этап 2: Backend — выдача истории и логов в API

### 2.1. Включить history/logs в список задач

**Файл:** `backend/server.js`

В `GET /api/projects/:projectId/tasks`:
- читать `<taskId>-history.json` и возвращать `history`
- добавить alias `executions` (если нужно для совместимости)
- вернуть `logs` (список log-файлов) из `<project>/.memory_bank/logs/`

### 2.2. Эндпоинты логов

**Файл:** `backend/server.js`

- `GET /api/projects/:projectId/tasks/:taskId/logs` → список файлов логов
- `GET /api/projects/:projectId/logs/:logFile` → содержимое лога (защита: только basename)

## Этап 3: Frontend — timeline + просмотр логов

### 3.1. Timeline компонент

**Файл:** `frontend/src/components/TaskTimeline.jsx`

- рендерить список запусков (по `startedAt`)
- показывать stage/status/model/duration/logFile
- по клику — выбирать запуск и его `logFile`

### 3.2. TaskDetailModal

**Файл:** `frontend/src/components/TaskDetailModal.jsx`

- показывать Timeline (`history`)
- показывать список логов (grouped by stage)
- по выбору файла запрашивать лог: `GET /api/projects/:projectId/logs/:logFile`
- когда задача `In Progress` — периодически обновлять лог (poll)

## Этап 4: Проверка

1. Запустить задачу и убедиться, что:
   - статус стал `In Progress`
   - создался log-файл
   - появилась запись в history
2. Остановить задачу:
   - статус стал `Failed`
   - запись в history обновилась (completedAt/duration)
3. Открыть TaskDetailModal:
   - timeline показывает оба запуска
   - можно выбрать запуск и увидеть соответствующий лог

## Приемочные критерии

1. ✅ История выполнения хранится в `<taskId>-history.json`
2. ✅ При запуске добавляется запись (`In Progress`, `startedAt`, `model`, `logFile`)
3. ✅ При завершении/остановке запись обновляется (`Done|Failed`, `completedAt`, `duration`)
4. ✅ В TaskDetailModal отображается timeline истории
5. ✅ Можно выбрать запуск и увидеть соответствующий лог
