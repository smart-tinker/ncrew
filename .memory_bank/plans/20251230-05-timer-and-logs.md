# План реализации: Timer and Logs

**Основан на спецификации:** `.memory_bank/tasks/04-timer-and-logs.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0  
**Статус:** Done

## Обзор

Добавить отображение таймера выполнения задачи и просмотр логов в реальном времени. Логи хранятся по отдельным файлам для каждого этапа.

## Предварительные требования

### Текущее состояние
- Логи хранятся в `.memory_bank/logs/` проекта
- Формат имени файла: `{taskId}-{timestamp}.log`
- Frontend имеет TaskCard компонент
- Backend имеет RUNNING_TASKS map для управления процессами

### Зависимости
- Задача 1 (System Settings) - Done
- Задача 3 (Workflow) - Done

## Этап 1: Backend - формат логов и остановка

### 1.1. Изменить формат имени файла логов

**Файл:** `backend/server.js`

**Задача:**
- Изменить формат имени файла логов на `{taskId}-{stage}-{timestamp}.log`
- Получить stage из фронтматтера задачи

**Псевдокод:**
```javascript
// При запуске задачи
const taskContent = await fs.readFile(taskFile, 'utf-8');
const frontmatter = parseFrontmatter(taskContent);
const timestamp = Date.now();
const logFile = path.join(logsDir, `${req.params.taskId}-${frontmatter.stage}-${timestamp}.log`);
```

### 1.2. API endpoint для остановки задачи

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `POST /api/tasks/:id/stop`
2. Найти процесс в RUNNING_TASKS
3. Убить процесс (process.kill())
4. Обновить статус задачи на `Failed` во фронтматтере
5. Остановить логирование

**Псевдокод:**
```javascript
app.post('/api/tasks/:id/stop', async (req, res) => {
  try {
    const { projectId } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${projectId}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);
    const tasksPath = path.join(config.path, '.memory_bank/tasks');
    const taskFile = path.join(tasksPath, `${req.params.id}.md`);

    if (!await fs.pathExists(taskFile)) {
      return res.status(404).json({ error: 'Task not found' });
    }

    const runningTask = RUNNING_TASKS.get(req.params.id);
    if (!runningTask) {
      return res.status(404).json({ error: 'Task not running' });
    }

    const { process } = runningTask;
    process.kill();

    const content = await fs.readFile(taskFile, 'utf-8');
    const updatedContent = updateFrontmatter(content, { status: 'Failed' });
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    res.json({
      taskId: req.params.id,
      status: 'Failed'
    });
  } catch (err) {
    console.error('Error stopping task:', err);
    res.status(500).json({ error: 'Failed to stop task' });
  }
});
```

## Этап 2: Frontend - таймер

### 2.1. Компонент TaskTimer

**Файл:** `frontend/src/components/TaskTimer.jsx`

**Содержимое:**
```jsx
import React, { useEffect, useState } from 'react';

export default function TaskTimer({ startTime }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!startTime) return;

    const interval = setInterval(() => {
      const now = Date.now();
      const diff = now - new Date(startTime).getTime();
      setElapsed(Math.floor(diff / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime]);

  const hours = Math.floor(elapsed / 3600);
  const minutes = Math.floor((elapsed % 3600) / 60);
  const seconds = elapsed % 60;

  return (
    <span style={{ fontFamily: 'monospace', fontSize: '14px' }}>
      {String(hours).padStart(2, '0')}:{String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}
    </span>
  );
}
```

### 2.2. Добавить таймер в TaskCard

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
- Добавить TaskTimer для задач со статусом `In Progress`
- Показывать рядом с кнопкой "Stop" (которую создадим позже)
- Использовать `task.startedAt` как startTime

**Псевдокод:**
```jsx
import TaskTimer from './TaskTimer';

// В TaskCard
{task.status === 'In Progress' && task.startedAt && (
  <TaskTimer startTime={task.startedAt} />
)}
```

### 2.3. Добавить startedAt в API response

**Файл:** `backend/server.js`

**Задача:**
- При запуске задачи возвращать `startedAt`
- Добавить поле в parseFrontmatter для извлечения `startedAt`

**Псевдокод:**
```javascript
// При запуске задачи
const startedAt = new Date().toISOString();
const updatedContent = updateFrontmatter(taskContent, { 
  status: 'Running',
  startedAt
});

// В API response
res.json({
  taskId: req.params.taskId,
  status: 'Running',
  startedAt
});
```

## Этап 3: Frontend - модалка деталей

### 3.1. Компонент TaskDetailModal

**Файл:** `frontend/src/components/TaskDetailModal.jsx`

**Содержимое:**
```jsx
import React from 'react';
import TaskTimer from './TaskTimer';

export default function TaskDetailModal({ task, onClose, onStopTask, onNextStage, models, onModelChange }) {
  return (
    <div className="modal-overlay">
      <div className="modal">
        <h2>{task.title}</h2>
        
        {task.status === 'In Progress' && task.startedAt && (
          <div style={{ marginBottom: '20px', fontSize: '24px' }}>
            ⏱ <TaskTimer startTime={task.startedAt} />
          </div>
        )}

        <div className="modal-body">
          <div style={{ marginBottom: '10px' }}>
            <strong>Stage:</strong> {task.stage}
          </div>
          <div style={{ marginBottom: '10px' }}>
            <strong>Status:</strong> <span className={`status-badge ${task.status.toLowerCase()}`}>{task.status}</span>
          </div>
          <div style={{ marginBottom: '10px' }}>
            <strong>Priority:</strong> {task.priority}
          </div>
          {task.model && (
            <div style={{ marginBottom: '10px' }}>
              <strong>Model:</strong> {task.model.fullName}
            </div>
          )}

          {/* Логи - MVP: показываем заглушку */}
          <div style={{ marginTop: '20px', padding: '10px', background: '#f5f5f5', borderRadius: '4px' }}>
            <strong>Logs:</strong>
            <div style={{ fontFamily: 'monospace', fontSize: '12px', marginTop: '10px', maxHeight: '200px', overflow: 'auto' }}>
              {task.status === 'In Progress' ? 'Running...' : 'No logs available yet.'}
            </div>
          </div>
        </div>
        
        <div className="modal-footer">
          <button className="button" onClick={onClose}>
            Close
          </button>
          {task.status === 'Done' && task.stage !== 'Verification' && (
            <button className="button" onClick={() => onNextStage(task.id)}>
              Next Stage
            </button>
          )}
          {task.status === 'In Progress' && (
            <button className="button" style={{ backgroundColor: '#e74c3c', color: 'white' }} onClick={() => onStopTask(task.id)}>
              Stop
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

### 3.2. Интеграция в ProjectView

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
- Добавить `detailTask` state
- При клике по карточке задачи открывать модалку деталей
- Добавить обработчики `handleStopTask` и `handleCloseDetail`

**Псевдокод:**
```jsx
const [detailTask, setDetailTask] = useState(null);

const handleStopTask = async (taskId) => {
  try {
    await axios.post(`/api/tasks/${taskId}/stop`, { projectId });
    setDetailTask(null);
    fetchTasks();
  } catch (err) {
    console.error('Error stopping task:', err);
    alert('Failed to stop task');
  }
};

const handleCloseDetail = () => {
  setDetailTask(null);
};

// В TaskCard добавить onClick
<div className={`card ${statusClass === 'failed' ? 'error' : ''}`} onClick={() => setDetailTask(task)}>

// В JSX
{detailTask && (
  <TaskDetailModal
    task={detailTask}
    onClose={handleCloseDetail}
    onStopTask={handleStopTask}
    onNextStage={handleNextStage}
    models={models}
    onModelChange={handleModelChange}
  />
)}
```

### 3.3. Добавить startedAt в parseFrontmatter

**Файл:** `backend/server.js`

**Задача:**
- Извлекать `startedAt` из фронтматтера

**Псевдокод:**
```javascript
// parseFrontmatter уже извлекает все поля, просто убедимся что startedAt попадает в результат
```

## Этап 4: Обновление задачи

### 4.1. Обновить фронтматтер задачи

**Файл:** `.memory_bank/tasks/04-timer-and-logs.md`

**Изменения:**
```yaml
---
title: Timer and Logs
stage: Implementation
status: In Progress
priority: High
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
specification: ../specs/20251230-05-timer-and-logs.md
plan: ../plans/20251230-05-timer-and-logs.md
---
```

## Этап 5: Тестирование

### 5.1. Проверка формата логов

**Сценарии:**
1. Запустить задачу
2. Проверить, что имя файла лога `{taskId}-{stage}-{timestamp}.log`
3. Проверить, что лог содержит информацию о startedAt

### 5.2. Проверка API endpoint остановки

**Сценарии:**
1. Запустить задачу
2. Вызвать `/api/tasks/:id/stop`
3. Проверить, что процесс остановлен
4. Проверить, что статус изменился на `Failed`

### 5.3. Проверка таймера

**Сценарии:**
1. Запустить задачу
2. Открыть карточку задачи
3. Проверить, что таймер отображается и тикает
4. Остановить задачу
5. Проверить, что таймер перестал обновляться

### 5.4. Проверка модалки деталей

**Сценарии:**
1. Кликнуть по карточке задачи
2. Проверить, что модалка открылась
3. Проверить, что все детали отображаются
4. Проверить, что таймер работает (если In Progress)
5. Проверить, что кнопка Stop останавливает задачу

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend)
2. Этап 2 (Frontend - таймер)
3. Этап 3 (Frontend - модалка)
4. Этап 4 (обновление задачи)
5. Этап 5 (тестирование)

## Приемочные критерии

После реализации проверить:
- ✅ Формат имени файла логов: `{taskId}-{stage}-{timestamp}.log`
- ✅ API endpoint `/api/tasks/:id/stop` работает
- ✅ Таймер отображается в карточке задачи (In Progress)
- ✅ Таймер отображается в модалке деталей
- ✅ Таймер останавливается при смене статуса на Done/Failed
- ✅ При клике по карточке открывается модалка с деталями
- ✅ В модалке отображаются все детали задачи
- ✅ Кнопка Stop в модалке останавливает задачу

## Примечания

1. **MVP упрощения:**
   - Логи в модалке пока без real-time обновления
   - Без отдельной модалки для логов
   - Логи пока без группировки по этапам

2. **В будущем:**
   - Real-time логи через WebSocket
   - Группировка логов по этапам
   - Отдельная модалка для логов

## Зависимости

### Требуется проверить:
- `parseFrontmatter()` извлекает `startedAt`
- RUNNING_TASKS map существует

## Время реализации

Оценка:
- Этап 1 (Backend): 1 час
- Этап 2 (Frontend таймер): 30 мин
- Этап 3 (Frontend модалка): 1 час
- Этап 4 (обновление): 5 мин
- Этап 5 (тестирование): 30 мин

**Итого:** 3 часа
