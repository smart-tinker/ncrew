# План реализации: Workflow (Stages)

**Основан на спецификации:** `.memory_bank/tasks/03-workflow-stages.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0  
**Статус:** Done

## Обзор

Добавить поддержку стадий (stages) в воркфлоу задач.

## Предварительные требования

### Текущее состояние
- Задачи уже имеют поле `stage` во фронтматтере
- Функция `parseFrontmatter()` существует
- Frontend имеет компоненты для карточек задач

### Зависимости
- Задача 1 (System Settings) - Done
- Задача 2 (Templates and Prompts) - Done

## Этап 1: Backend - поддержка стадий

### 1.1. Обновить parseFrontmatter()

**Файл:** `backend/server.js`

**Задача:**
- Добавить извлечение поля `stage` из фронтматтера
- Дефолтное значение: `Specification`

**Псевдокод:**
```javascript
function parseFrontmatter(content) {
  const frontmatterMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!frontmatterMatch) {
    return { stage: 'Specification', status: 'New' };
  }

  const frontmatter = frontmatterMatch[1];
  const lines = frontmatter.split('\n');
  const result = {};

  for (const line of lines) {
    const [key, ...valueParts] = line.split(':');
    if (key && valueParts.length > 0) {
      const value = valueParts.join(':').trim();
      result[key.trim()] = value.replace(/^"|"$/g, '');
    }
  }

  if (!result.stage) {
    result.stage = 'Specification';
  }

  return result;
}
```

### 1.2. Обновить updateFrontmatter()

**Файл:** `backend/server.js`

**Задача:**
- Убедиться, что функция обновляет поле `stage`
- Уже реализовано в задаче 1

### 1.3. API endpoint для смены стадии

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `POST /api/tasks/:id/next-stage`
2. Логика смены стадии:
   - Specification → Plan → Implementation → Verification
3. При смене стадии статус устанавливается в `New`
4. Если уже на последней стадии - вернуть ошибку

**Псевдокод:**
```javascript
const STAGES = ['Specification', 'Plan', 'Implementation', 'Verification'];

app.post('/api/tasks/:id/next-stage', async (req, res) => {
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

    const content = await fs.readFile(taskFile, 'utf-8');
    const frontmatter = parseFrontmatter(content);
    
    const currentIndex = STAGES.indexOf(frontmatter.stage);
    if (currentIndex === -1 || currentIndex === STAGES.length - 1) {
      return res.status(400).json({ error: 'Already at last stage' });
    }

    const nextStage = STAGES[currentIndex + 1];
    const updatedContent = updateFrontmatter(content, {
      stage: nextStage,
      status: 'New'
    });
    
    await fs.writeFile(taskFile, updatedContent, 'utf-8');

    res.json({
      taskId: req.params.id,
      stage: nextStage,
      status: 'New'
    });
  } catch (err) {
    console.error('Error moving task to next stage:', err);
    res.status(500).json({ error: 'Failed to move task to next stage' });
  }
});
```

## Этап 2: Frontend - визуализация стадий

### 2.1. Обновить TaskCard компонент

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
- Добавить отображение стадии в карточке задачи
- Добавить бейдж для стадии с цветовой индикацией

**Псевдокод:**
```jsx
const stageColors = {
  Specification: '#1976d2',  // синий
  Plan: '#7b1fa2',            // фиолетовый
  Implementation: '#f57c00', // оранжевый
  Verification: '#388e3c'     // зеленый
};

function TaskCard({ task, onRunClick, onModelChange, onNextStage }) {
  const statusClass = task.status.toLowerCase();
  
  return (
    <div className={`card ${statusClass === 'failed' ? 'error' : ''}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ flex: 1 }}>
          <h4>{task.title}</h4>
          <div style={{ marginTop: '8px', display: 'flex', gap: '10px', alignItems: 'center' }}>
            <span className="stage-badge" style={{ backgroundColor: stageColors[task.stage] }}>
              {task.stage}
            </span>
            <span className={`status-badge ${statusClass}`}>{task.status}</span>
            <span style={{ color: '#999', fontSize: '12px' }}>
              Priority: {task.priority}
            </span>
          </div>
          {/* ... остальной код ... */}
        </div>
        <div style={{ display: 'flex', gap: '10px', marginLeft: '20px' }}>
          {task.status === 'Done' && task.stage !== 'Verification' && (
            <button className="button" onClick={() => onNextStage(task.id)}>
              Next Stage
            </button>
          )}
          <button
            className={`button ${task.status === 'Running' ? 'success' : 'primary'}`}
            onClick={() => onRunClick(task)}
            disabled={task.status === 'Running'}
          >
            {task.status === 'Running' ? 'Running...' : 'Run'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 2.2. Обновить CSS для stage-badge

**Файл:** `frontend/src/index.css`

**Задача:**
- Добавить стили для `.stage-badge`

**Псевдокод:**
```css
.stage-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  color: white;
}
```

### 2.3. Добавить обработчик onNextStage

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
- Добавить функцию `handleNextStage`
- Вызывать API endpoint `/api/tasks/:id/next-stage`
- Обновить список задач после перехода

**Псевдокод:**
```jsx
const handleNextStage = async (taskId) => {
  try {
    await axios.post(`/api/tasks/${taskId}/next-stage`, { projectId });
    fetchTasks();
  } catch (err) {
    console.error('Error moving task to next stage:', err);
    alert(err.response?.data?.error || 'Failed to move task to next stage');
  }
};
```

## Этап 3: Обновление задачи

### 3.1. Обновить фронтматтер задачи

**Файл:** `.memory_bank/tasks/03-workflow-stages.md`

**Изменения:**
```yaml
---
title: Workflow (Stages)
stage: Implementation
status: In Progress
priority: High
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
specification: ../specs/20251230-04-workflow-stages.md
plan: ../plans/20251230-04-workflow-stages.md
---
```

## Этап 4: Тестирование

### 4.1. Проверка API endpoint

**Сценарии:**
1. Создать задачу без поля `stage`
2. Проверить, что дефолтное значение `Specification`
3. Вызвать `/api/tasks/:id/next-stage`
4. Проверить, что стадия изменилась на `Plan`
5. Проверить, что статус изменился на `New`
6. Повторить для всех стадий
7. Попробовать перейти с последней стадии - должно вернуть ошибку

### 4.2. Проверка Frontend

**Сценарии:**
1. Открыть страницу проекта
2. Проверить, что стадия отображается в карточке
3. Проверить цветовую индикацию
4. Проверить, что кнопка "Next Stage" показывается только при статусе `Done`
5. Нажать кнопку "Next Stage" - стадия должна измениться
6. Проверить, что на последней стадии кнопка не показывается

### 4.3. Проверка обратной совместимости

**Сценарии:**
1. Создать задачу без поля `stage`
2. Проверить, что она дефолтит к `Specification`
3. Проверить, что она отображается корректно в UI

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend - поддержка стадий)
2. Этап 2 (Frontend - визуализация)
3. Этап 3 (обновление задачи)
4. Этап 4 (тестирование)

## Приемочные критерии

После реализации проверить:
- ✅ Фронтматтер задачи содержит поле `stage`
- ✅ Дефолтное значение `Specification` для новых задач
- ✅ Кнопка "Next Stage" появляется только при статусе `Done`
- ✅ При нажатии кнопки стадия меняется последовательно
- ✅ Статус автоматически сбрасывается на `New` при смене стадии
- ✅ Стадия визуально отображается в карточке задачи
- ✅ На последней стадии (Verification) кнопка "Next Stage" не показывается
- ✅ Цветовая индикация стадий работает корректно

## Примечания

1. **Константы:** Использовать константу `STAGES` для определения порядка смены
2. **Цвета:** Использовать указанные цвета для каждой стадии
3. **Валидация:** Проверять, что стадия существует в списке `STAGES`
4. **Обратная совместимость:** Задачи без `stage` дефолтят к `Specification`

## Зависимости

### Требуется проверить:
- `parseFrontmatter()` существует
- `updateFrontmatter()` существует
- TaskCard компонент существует

## Время реализации

Оценка:
- Этап 1 (Backend): 1 час
- Этап 2 (Frontend): 1 час
- Этап 3 (обновление задачи): 5 минут
- Этап 4 (тестирование): 30 минут

**Итого:** 2.5 часа
