# План реализации: Project Edit Modal

**Основан на спецификации:** `.memory_bank/tasks/06-project-edit-modal.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0  
**Статус:** Done

## Обзор

Добавить возможность редактирования настроек уже добавленного проекта через модальное окно.

## Предварительные требования

### Текущее состояние
- API GET /api/projects существует
- Компонент ProjectView существует
- ModelSelector компонент существует

### Зависимости
- Задача 1 (System Settings) - Done
- Задача 2 (Templates and Prompts) - Done

## Этап 1: Backend

### 1.1. API endpoint для редактирования проекта

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `PUT /api/projects/:id`
2. Проверить существование worktree с текущим префиксом
3. Если есть - вернуть предупреждение
4. Обновить конфиг проекта

**Псевдокод:**
```javascript
app.put('/api/projects/:id', async (req, res) => {
  try {
    const { name, worktreePrefix, defaultModel } = req.body;
    const configPath = path.join(SETTINGS_DIR, `${req.params.id}.json`);

    if (!await fs.pathExists(configPath)) {
      return res.status(404).json({ error: 'Project not found' });
    }

    const config = await fs.readJson(configPath);

    if (worktreePrefix && config.worktreePrefix && worktreePrefix !== config.worktreePrefix) {
      const worktreesPath = path.join(config.path, 'worktrees');
      if (await fs.pathExists(worktreesPath)) {
        const existingWorktrees = await fs.readdir(worktreesPath);
        const hasWorktreesWithPrefix = existingWorktrees.some(w => w.startsWith(config.worktreePrefix));
        
        if (hasWorktreesWithPrefix) {
          return res.json({
            warning: 'Changing worktree prefix will not affect existing worktrees. Old worktrees will remain.',
            project: { ...config, name: name || config.name, worktreePrefix: worktreePrefix || config.worktreePrefix }
          });
        }
      }
    }

    const updatedConfig = {
      ...config,
      name: name || config.name,
      worktreePrefix: worktreePrefix || config.worktreePrefix
    };

    if (defaultModel) {
      updatedConfig.defaultModel = defaultModel;
    }

    await fs.writeJson(configPath, updatedConfig, { spaces: 2 });

    res.json(updatedConfig);
  } catch (err) {
    console.error('Error updating project:', err);
    res.status(500).json({ error: 'Failed to update project' });
  }
});
```

## Этап 2: Frontend

### 2.1. Компонент ProjectEditModal

**Файл:** `frontend/src/components/ProjectEditModal.jsx`

**Содержимое:**
```jsx
import React from 'react';
import ModelSelector from './ModelSelector';

export default function ProjectEditModal({ project, onSave, onCancel, models }) {
  const [name, setName] = React.useState(project.name);
  const [worktreePrefix, setWorktreePrefix] = React.useState(project.worktreePrefix || 'task-');
  const [selectedModel, setSelectedModel] = React.useState(project.defaultModel?.fullName || '');

  const handleSave = () => {
    if (!selectedModel) {
      onSave({ name, worktreePrefix, defaultModel: null });
      return;
    }

    const [modelProvider, modelName] = selectedModel.split('/');
    const defaultModel = {
      agenticHarness: 'opencode',
      modelProvider,
      modelName
    };

    onSave({ name, worktreePrefix, defaultModel });
  };

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>Edit Project</h2>
        
        <div className="modal-body">
          <label className="label">Name</label>
          <input
            className="input"
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
          />

          <label className="label">Worktree Prefix</label>
          <input
            className="input"
            type="text"
            value={worktreePrefix}
            onChange={e => setWorktreePrefix(e.target.value)}
          />

          <label className="label">Default Model</label>
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onSelect={setSelectedModel}
          />

          <div style={{ marginTop: '20px', padding: '10px', background: '#fff3cd', borderRadius: '4px', fontSize: '14px' }}>
            <strong>Path:</strong> {project.path} (read-only)
          </div>
        </div>
        
        <div className="modal-footer">
          <button className="button" onClick={onCancel}>
            Cancel
          </button>
          <button className="button primary" onClick={handleSave}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 2.2. Интеграция в ProjectView

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
1. Добавить state `editProject`
2. Добавить функцию `handleEditClick`
3. Добавить функцию `handleEditSave`
4. Добавить кнопку "Edit" на странице проекта
5. Добавить ProjectEditModal в JSX

**Псевдокод:**
```jsx
const [editProject, setEditProject] = useState(null);

const handleEditClick = () => {
  setEditProject(project);
};

const handleEditSave = async (updatedConfig) => {
  try {
    await axios.put(`/api/projects/${project.id}`, updatedConfig);
    fetchProject();
    setEditProject(null);
  } catch (err) {
    console.error('Error updating project:', err);
    alert(err.response?.data?.error || 'Failed to update project');
  }
};

// В JSX после project card
<button className="button" onClick={handleEditClick}>
  Edit
</button>

{editProject && (
  <ProjectEditModal
    project={editProject}
    models={models}
    onSave={handleEditSave}
    onCancel={() => setEditProject(null)}
  />
)}
```

## Этап 3: Обновление задачи

### 3.1. Обновить фронтматтер задачи

**Файл:** `.memory_bank/tasks/06-project-edit-modal.md`

**Изменения:**
```yaml
---
title: Project Edit Modal
stage: Implementation
status: In Progress
priority: Medium
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
specification: ../specs/20251230-07-project-edit-modal.md
plan: ../plans/20251230-07-project-edit-modal.md
---
```

## Этап 4: Тестирование

### 4.1. Проверка API endpoint

**Сценарии:**
1. Создать проект
2. Изменить название
3. Изменить worktreePrefix без существующих worktrees
4. Попытаться изменить worktreePrefix с существующими worktree

### 4.2. Проверка Frontend

**Сценарии:**
1. Открыть страницу проекта
2. Нажать кнопку "Edit"
3. Проверить, что все поля отображаются
4. Изменить название и сохранить
5. Проверить, что название обновилось

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend)
2. Этап 2 (Frontend)
3. Этап 3 (обновление задачи)
4. Этап 4 (тестирование)

## Приемочные критерии

После реализации проверить:
- ✅ На странице проекта есть кнопка "Edit"
- ✅ При нажатии открывается модалка редактирования
- ✅ Можно редактировать `name`, `worktreePrefix`, `defaultModel`
- ✅ Поле `path` только для чтения
- ✅ При изменении `worktreePrefix` показывается предупреждение (если нужно)
- ✅ При сохранении настройки обновляются в конфиге проекта

## Примечания

1. **Простая задача:** Функционал простой, не требует сложной логики
2. **Скорость:** Быстрая реализация
3. **Безопасность:** Поле path read-only

## Зависимости

### Требуется проверить:
- `fs.readdir()` для проверки worktrees
- ModelSelector компонент существует

## Время реализации

Оценка:
- Этап 1 (Backend): 30 мин
- Этап 2 (Frontend): 30 мин
- Этап 3 (обновление): 5 мин
- Этап 4 (тестирование): 15 мин

**Итого:** 1.25 часа
