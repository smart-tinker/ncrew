# Спецификация: Task Execution History

**Имя:** Task Execution History  
**Дата:** 2025-12-30  
**Версия:** 1.1  
**Статус:** Done

## Обзор

Добавить визуализацию истории запусков задачи по этапам и удобный просмотр логов каждого запуска.

## User Stories

### US-7.1: История выполнения
Как **Разработчик**, я хочу видеть историю запусков задачи по этапам, чтобы понимать, что было выполнено на каждом этапе.

## Требования

### Функциональные требования

#### 1. Хранение истории (выбранный вариант)

История хранится в отдельном файле рядом с задачами:

```
<project>/.memory_bank/tasks/<taskId>-history.json
```

Пример структуры:

```json
{
  "history": [
    {
      "id": "run-1767132827804",
      "stage": "Verification",
      "status": "Failed",
      "startedAt": "2025-12-30T22:13:47.804Z",
      "completedAt": "2025-12-30T22:13:56.982Z",
      "duration": 9178,
      "model": {
        "agenticHarness": "opencode",
        "modelProvider": "opencode",
        "modelName": "claude-sonnet-4-5",
        "fullName": "opencode/claude-sonnet-4-5"
      },
      "logFile": "01-system-settings-verification-1767132827804.log"
    }
  ]
}
```

#### 2. Визуализация

В `TaskDetailModal` показывать timeline запусков (все записи history) и давать выбрать лог-файл конкретного запуска.

#### 3. Backend

- При запуске задачи добавлять запись в `<taskId>-history.json` со статусом `In Progress`
- При завершении/остановке обновлять соответствующую запись (`status`, `completedAt`, `duration`)
- В `GET /api/projects/:id/tasks` включать `history`/`executions` и список доступных логов

#### 4. Frontend

- Обновить `TaskDetailModal` для отображения истории и логов по файлам
- Показывать время выполнения (duration) и использованную модель (model)
- При выборе запуска подсвечивать его лог и показывать содержимое

## Приемочные критерии

1. ✅ История выполнения хранится в `<taskId>-history.json`
2. ✅ При запуске задачи добавляется запись в историю со статусом `In Progress`
3. ✅ При завершении/остановке запись обновляется (status/completedAt/duration)
4. ✅ TaskDetailModal показывает timeline истории
5. ✅ Для каждого запуска отображаются duration и model
6. ✅ Можно выбрать запуск и посмотреть его лог
