---
title: Task Execution History
stage: Specification
status: New
priority: Medium
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
---

# Description

Добавить визуализацию истории выполнения задачи по этапам (Timeline). Позволить просматривать историю запусков на каждом этапе.

## Requirements

### История выполнения

Хранить информацию о каждом запуске задачи:
- Этап (stage)
- Статус (Done/Failed)
- Время старта
- Время завершения
- Длительность
- Путь к логам

### Хранение истории

**Вариант A:** В отдельном файле
```
.memory_bank/tasks/
  task-1.md              # Задача
  task-1-history.json    # История
```

**Вариант B:** Во фронтматтере (плохо для большого объема)
**Вариант C:** В конфиге проекта (для всех задач)

**Предлагаем: Вариант A** - отдельный JSON файл для каждой задачи

```json
{
  "history": [
    {
      "id": "run-1234567890",
      "stage": "Specification",
      "status": "Done",
      "startedAt": "2025-12-30T10:00:00Z",
      "completedAt": "2025-12-30T10:01:23Z",
      "duration": 83000,
      "model": {
        "agenticHarness": "opencode",
        "modelProvider": "opencode",
        "modelName": "claude-sonnet-4-5"
      },
      "logFile": "task-1-specification-1234567890.log"
    },
    {
      "id": "run-1234567891",
      "stage": "Plan",
      "status": "In Progress",
      "startedAt": "2025-12-30T10:02:00Z",
      "completedAt": null,
      "duration": null,
      "model": {
        "agenticHarness": "opencode",
        "modelProvider": "opencode",
        "modelName": "claude-sonnet-4-5"
      },
      "logFile": "task-1-plan-1234567891.log"
    }
  ]
}
```

### Timeline визуализация

**В детальном просмотре задачи:**

```
┌─ Specification ───────────────────────────┐
│ ✓ Done (00:01:23)                          │
│   2025-12-30 10:00 - 10:01                 │
│   Model: opencode/claude-sonnet-4-5        │
└────────────────────────────────────────────┘
┌─ Plan ─────────────────────────────────────┐
│ ← Current: In Progress (00:00:45)           │
│   2025-12-30 10:02 - running              │
│   Model: opencode/claude-sonnet-4-5        │
└────────────────────────────────────────────┘
┌─ Implementation ───────────────────────────┐
│ New                                         │
└────────────────────────────────────────────┘
┌─ Verification ─────────────────────────────┐
│ New                                         │
└────────────────────────────────────────────┘
```

**Стили:**
- Done: зеленая рамка
- In Progress: оранжевая рамка, пульсация
- New: серая рамка
- Failed: красная рамка

**Интерактивность:**
- Клик по этапу → показывает логи конкретного этапа
- В модалке детального просмотра

### Требования к реализации

1. **Backend**
   - При запуске задачи: добавлять запись в историю
   - При завершении задачи: обновлять запись (completedAt, duration, status)
   - API endpoint для получения истории: `GET /api/tasks/:id/history`
   - Обновить объект задачи для включения истории

2. **Frontend**
   - Компонент `TaskTimeline` для отображения timeline
   - В модалке детального просмотра добавить timeline
   - При клике по этапу → открывает логи конкретного запуска

3. **UI**
   - Timeline визуализирован как блоки с информацией
   - Цветовая индикация статуса
   - Таймлайны отображаются в хронологическом порядке

## Dependencies

- Зависит от: Задача 1 (System Settings), Задача 3 (Workflow), Задача 4 (Timer and Logs)
- Блокирует: -

## Acceptance Criteria

- ✅ При запуске задачи запись добавляется в историю
- ✅ При завершении задачи запись обновляется (completedAt, duration, status)
- ✅ API endpoint `GET /api/tasks/:id/history` возвращает историю
- ✅ Timeline визуализируется в модалке детального просмотра
- ✅ Timeline показывает информацию о каждом запуске
- ✅ Цветовая индикация статуса этапа
- ✅ Клик по этапу открывает логи конкретного запуска
- ✅ Для In Progress показывается текущая длительность
