# Спецификация: Task Execution History

**Имя:** Task Execution History  
**Дата:** 2025-12-30  
**Версия:** 1.0  
**Статус:** Done

## Обзор

Добавить визуализацию истории выполнения задачи по этапам. Позволить просматривать историю запусков на каждом этапе.

## User Stories

### US-7.1: История выполнения
Как **Разработчик**, я хочу видеть историю запусков задачи по этапам, чтобы понимать, что было выполнено на каждом этапе.

## Требования

### Функциональные требования

#### 1. Хранение истории

**Вариант A (упрощенный MVP):** Хранить историю во фронтматтере задачи

```yaml
---
title: Task Name
stage: Implementation
status: Done
priority: High
executions:
  - stage: Specification
    status: Done
    startedAt: "2025-12-30T10:00:00Z"
    completedAt: "2025-12-30T10:01:23Z"
    duration: 83000
    model: opencode/claude-sonnet-4-5
  - stage: Plan
    status: Done
    startedAt: "2025-12-30T10:02:00Z"
    completedAt: "2025-12-30T10:03:00Z"
    duration: 60000
    model: opencode/claude-sonnet-4-5
```

#### 2. Визуализация

**Простая MVP:** Показывать только последнюю информацию в TaskDetailModal

```jsx
<div>
  <strong>Last Execution:</strong> {task.lastExecution.stage} - {task.lastExecution.status}
  <strong>Duration:</strong> {formatDuration(task.lastExecution.duration)}
</div>
```

#### 3. Backend

- Добавить поле `executions` в parseFrontmatter
- При запуске задачи добавлять запись в историю
- При завершении обновлять запись

#### 4. Frontend

- Обновить TaskDetailModal для отображения истории
- Показывать время выполнения
- Показывать использованную модель

## Приемочные критерии

1. ✅ История выполнения хранится во фронтматтере задачи
2. ✅ При запуске задачи добавляется запись в историю
3. ✅ При завершении обновляется запись в истории
4. ✅ TaskDetailModal показывает историю выполнения
5. ✅ Отображается время выполнения
6. ✅ Отображается использованная модель
