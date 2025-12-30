# План реализации: Task Execution History

**Основан на спецификации:** `.memory_bank/tasks/07-task-execution-history.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0

## Обзор

MVP для визуализации истории выполнения задачи.

## Предварительные требования

### Текущее состояние
- parseFrontmatter существует
- TaskDetailModal существует
- Формат имени файла логов: `{taskId}-{stage}-{timestamp}.log`

### Зависимости
- Все предыдущие задачи Done

## Этап 1: Backend - история в фронтматтере

### 1.1. Обновить parseFrontmatter

**Файл:** `backend/server.js`

**Задача:**
- Добавить извлечение поля `executions`
- Дефолтное значение: `[]`

**Псевдокод:**
```javascript
// В parseFrontmatter
result.executions = result.executions || [];
```

### 1.2. Добавление записи в историю при запуске

**Файл:** `backend/server.js`

**Задача:**
- При запуске задачи добавлять запись в массив `executions`

**Псевдокод:**
```javascript
const execution = {
  stage: frontmatter.stage,
  status: 'In Progress',
  startedAt: startedAt,
  completedAt: null,
  duration: null,
  model: { ...model }
};

const executions = frontmatter.executions || [];
executions.push(execution);

const updatedContent = updateFrontmatter(taskContent, { 
  status: 'Running', 
  startedAt,
  executions
});
```

### 1.3. Обновление записи при завершении

**Файл:** `backend/server.js`

**Задача:**
- При завершении обновлять последнюю запись

**Псевдокод:**
```javascript
// В process.on('close')
const completedAt = new Date().toISOString();
const duration = new Date(completedAt).getTime() - new Date(startedAt).getTime();

const content = await fs.readFile(taskFile, 'utf-8');
const frontmatter = parseFrontmatter(content);

if (frontmatter.executions && frontmatter.executions.length > 0) {
  const lastExecution = frontmatter.executions[frontmatter.executions.length - 1];
  lastExecution.completedAt = completedAt;
  lastExecution.duration = duration;
  lastExecution.status = exitCode === 0 ? 'Done' : 'Failed';
  
  const newContent = updateFrontmatter(content, {
    status: lastExecution.status,
    executions: frontmatter.executions
  });
  
  await fs.writeFile(taskFile, newContent, 'utf-8');
}
```

## Этап 2: Frontend - визуализация истории

### 2.1. Обновить API response

**Файл:** `backend/server.js`

**Задача:**
- Добавить поле `executions` в ответ задач

**Псевдокод:**
```javascript
tasks.push({
  id: taskId,
  title,
  status,
  priority,
  stage,
  startedAt,
  model: {...},
  executions: frontmatter.executions || []
});
```

### 2.2. Обновить TaskDetailModal

**Файл:** `frontend/src/components/TaskDetailModal.jsx`

**Задача:**
- Добавить секцию истории
- Показывать последнее выполнение

**Псевдокод:**
```jsx
<div style={{ marginTop: '20px', padding: '10px', background: '#f5f5f5', borderRadius: '4px' }}>
  <strong>History:</strong>
  {task.executions && task.executions.length > 0 ? (
    <div>
      <div><strong>Last:</strong> {task.executions[task.executions.length - 1].stage} - {task.executions[task.executions.length - 1].status}</div>
      {task.executions[task.executions.length - 1].duration && (
        <div><strong>Duration:</strong> {formatDuration(task.executions[task.executions.length - 1].duration)}</div>
      )}
    </div>
  ) : (
    <div>No executions yet.</div>
  )}
</div>

// Добавить функцию formatDuration
function formatDuration(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else {
    return `${seconds}s`;
  }
}
```

## Этап 3: Обновление задачи

### 3.1. Обновить фронтматтер задачи

**Файл:** `.memory_bank/tasks/07-task-execution-history.md`

**Изменения:**
```yaml
---
title: Task Execution History
stage: Implementation
status: In Progress
priority: Medium
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
specification: ../specs/20251230-08-task-execution-history.md
plan: ../plans/20251230-08-task-execution-history.md
---
```

## Этап 4: Тестирование

### 4.1. Проверка истории во фронтматтере

**Сценарии:**
1. Создать задачу
2. Проверить, что поле `executions` дефолтит к `[]`
3. Запустить задачу
4. Проверить, что запись добавляется
5. Остановить задачу
6. Проверить, что запись обновляется

### 4.2. Проверка визуализации

**Сценарии:**
1. Открыть TaskDetailModal для задачи
2. Проверить, что история отображается
3. Проверить, что показывается последнее выполнение
4. Проверить формат времени

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend)
2. Этап 2 (Frontend)
3. Этап 3 (обновление задачи)
4. Этап 4 (тестирование)

## Приемочные критерии

После реализации проверить:
- ✅ История выполнения хранится во фронтматтере задачи
- ✅ При запуске задачи добавляется запись в историю
- ✅ При завершении записи обновляется
- ✅ TaskDetailModal показывает историю выполнения
- ✅ Показывается последнее выполнение (stage, status, duration)
- ✅ Форматирование времени работает корректно

## Примечания

1. **MVP упрощения:**
   - Показываем только последнее выполнение
   - Без timeline визуализации
   - Без отдельной модалки для логов
   - История хранится в фронтматтере (не отдельный файл)

2. **В будущем:**
   - Отдельный файл истории (`{taskId}-history.json`)
   - Timeline визуализация по этапам
   - Детальный просмотр каждой записи

## Зависимости

### Требуется проверить:
- `parseFrontmatter()` существует
- `updateFrontmatter()` существует
- TaskDetailModal компонент существует

## Время реализации

Оценка:
- Этап 1 (Backend): 45 мин
- Этап 2 (Frontend): 30 мин
- Этап 3 (обновление): 5 мин
- Этап 4 (тестирование): 15 мин

**Итого:** 1.5 часа
