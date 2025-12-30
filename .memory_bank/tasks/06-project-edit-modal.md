---
title: Project Edit Modal
stage: Specification
status: New
priority: Medium
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
---

# Description

Добавить возможность редактирования настроек уже добавленного проекта через модальное окно.

## Requirements

### Редактируемые поля

- `name` - название проекта
- `worktreePrefix` - префикс для работы
- `defaultModel` - дефолтная модель

### Read-only поля

- `path` - путь к проекту (не редактируется)

### Предупреждение при изменении worktreePrefix

Если пользователь меняет `worktreePrefix` и в проекте уже есть worktree с другим префиксом:
1. Показать предупреждение: "Изменение префикса не повлияет на существующие worktree. Старые worktree останутся."
2. Позволить сохранить изменения
3. Новые worktree создаются с новым префиксом

### Требования к реализации

1. **Backend**
   - API endpoint: `PUT /api/projects/:id`
   - Request body:
     ```json
     {
       "name": "Updated Name",
       "worktreePrefix": "feat-",
       "defaultModel": {
         "agenticHarness": "opencode",
         "modelProvider": "opencode",
         "modelName": "claude-sonnet-4-5"
       }
     }
   ```
   - Проверить существование worktree с текущим префиксом
   - Обновить конфиг проекта
   - Валидация модели (уже реализовано)

2. **Frontend**
   - Компонент `ProjectEditModal`
   - Props:
     - `project` - текущий проект
     - `onSave` - callback при сохранении
     - `onCancel` - callback при отмене
   - Форма с полями для редактирования
   - Выбор модели через `ModelSelector`
   - Предупреждение для `worktreePrefix`

3. **UI**
   - Кнопка "Edit" на карточке проекта (на странице проекта)
   - При нажатии открывается модалка
   - Форма с полями:
     - Name (input)
     - Worktree Prefix (input)
     - Default Model (ModelSelector)
   - Кнопки: "Save", "Cancel"
   - Предупреждение (если меняется worktreePrefix)

### Проверка существования worktree

```javascript
const existingWorktrees = await fs.readdir(path.join(projectPath, 'worktrees'));
const hasWorktreesWithPrefix = existingWorktrees.some(w => w.startsWith(oldPrefix));
```

## Dependencies

- Зависит от: -
- Блокирует: -

## Acceptance Criteria

- ✅ На странице проекта есть кнопка "Edit"
- ✅ При нажатии открывается модалка редактирования
- ✅ Можно редактировать `name`, `worktreePrefix`, `defaultModel`
- ✅ Поле `path` только для чтения
- ✅ При изменении `worktreePrefix` показывается предупреждение
- ✅ При сохранении настройки обновляются в конфиге проекта
- ✅ API endpoint `PUT /api/projects/:id` работает корректно
