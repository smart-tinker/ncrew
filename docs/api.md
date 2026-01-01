# API Reference (NCrew)

Документация по текущим API endpoints NCrew (MVP).

## Base URL

```
http://localhost:3001/api
```

## Auth

В текущей версии аутентификация не реализована.

## Errors

Большинство ошибок возвращаются в виде:

```json
{
  "error": "Message"
}
```

## Models

### Get Models Cache

```http
GET /api/models
```

**Response 200:**
```json
{
  "models": [
    { "provider": "opencode", "name": "claude-sonnet-4-5", "fullName": "opencode/claude-sonnet-4-5" }
  ],
  "cachedAt": "2025-12-30T20:00:00.000Z",
  "expiresAt": "2025-12-31T20:00:00.000Z"
}
```

**Response 503 (если `opencode` недоступен):**
```json
{ "error": "opencode not found in PATH or failed to execute" }
```

### Refresh Models Cache

```http
POST /api/models/refresh
```

Ответ такой же, как у `GET /api/models`.

## Projects

### List Projects

```http
GET /api/projects
```

**Response 200:**
```json
[
  {
    "id": "ncrew",
    "name": "NCrew",
    "path": "/home/dadgo/code/ncrew",
    "worktreePrefix": "wt-",
    "defaultModel": {
      "agenticHarness": "opencode",
      "modelProvider": "opencode",
      "modelName": "claude-sonnet-4-5",
      "fullName": "opencode/claude-sonnet-4-5"
    },
    "isAccessible": true,
    "error": null
  }
]
```

### Create Project

```http
POST /api/projects
```

**Request body:**
```json
{
  "name": "My Project",
  "path": "/abs/path/to/repo",
  "worktreePrefix": "task-",
  "defaultModel": {
    "agenticHarness": "opencode",
    "modelProvider": "opencode",
    "modelName": "claude-sonnet-4-5"
  }
}
```

Примечания:
- `id` проекта вычисляется из `name` (lowercase + пробелы → `-`).
- `defaultModel` опционален.

**Response 200:**
```json
{
  "id": "my-project",
  "name": "My Project",
  "path": "/abs/path/to/repo",
  "worktreePrefix": "task-",
  "isAccessible": true,
  "defaultModel": {
    "agenticHarness": "opencode",
    "modelProvider": "opencode",
    "modelName": "claude-sonnet-4-5",
    "fullName": "opencode/claude-sonnet-4-5"
  }
}
```

**Response 400 (примеры):**
```json
{ "error": "Name and path are required" }
```
```json
{ "error": "Project path not accessible" }
```
```json
{ "error": "Project already exists" }
```
```json
{ "error": "Selected model not available" }
```

### Update Project

```http
PUT /api/projects/:id
```

**Request body (любые поля):**
```json
{
  "name": "Updated Name",
  "worktreePrefix": "feat-",
  "defaultModel": null
}
```

Примечания:
- `defaultModel: null` удаляет дефолтную модель из конфига проекта.
- При смене `worktreePrefix`, если уже есть worktree со старым префиксом, backend вернёт “предупреждение” и потребует подтверждения.

**Response 200 (обычный):**
```json
{
  "id": "my-project",
  "name": "Updated Name",
  "path": "/abs/path/to/repo",
  "worktreePrefix": "feat-",
  "defaultModel": null,
  "isAccessible": true
}
```

**Response 200 (требуется подтверждение смены префикса):**
```json
{
  "warning": "Changing worktree prefix will not affect existing worktrees. Old worktrees will remain.",
  "requiresConfirmation": true,
  "project": {
    "id": "my-project",
    "name": "Updated Name",
    "path": "/abs/path/to/repo",
    "worktreePrefix": "feat-",
    "defaultModel": null,
    "isAccessible": true
  }
}
```

Чтобы подтвердить смену префикса — повторите запрос, добавив:

```json
{
  "confirmWorktreePrefixChange": true
}
```

## Tasks

### List Tasks (by Project)

```http
GET /api/projects/:projectId/tasks
```

**Response 200 (пример одного элемента):**
```json
[
  {
    "id": "01-system-settings",
    "title": "System Settings (~/.ncrew)",
    "status": "New",
    "priority": "High",
    "stage": "Specification",
    "startedAt": null,
    "model": {
      "agenticHarness": "opencode",
      "modelProvider": "opencode",
      "modelName": "claude-sonnet-4-5",
      "fullName": "opencode/claude-sonnet-4-5"
    },
    "history": [],
    "executions": [],
    "logs": [
      { "file": "01-system-settings-specification-1767130000000.log", "stage": "specification", "timestamp": 1767130000000 }
    ]
  }
]
```

### Update Task Model

```http
PUT /api/tasks/:taskId/model
```

**Request body:**
```json
{
  "projectId": "my-project",
  "model": {
    "agenticHarness": "opencode",
    "modelProvider": "opencode",
    "modelName": "gpt-5.2"
  }
}
```

**Response 200:**
```json
{
  "taskId": "zz-stage-test",
  "model": {
    "agenticHarness": "opencode",
    "modelProvider": "opencode",
    "modelName": "gpt-5.2",
    "fullName": "opencode/gpt-5.2"
  }
}
```

### Run Task

```http
POST /api/tasks/:taskId/run
```

**Request body:**
```json
{
  "projectId": "my-project",
  "model": {
    "agenticHarness": "opencode",
    "modelProvider": "opencode",
    "modelName": "claude-sonnet-4-5"
  }
}
```

**Response 200:**
```json
{
  "status": "In Progress",
  "message": "Task started successfully",
  "taskId": "01-system-settings",
  "worktreePath": "/abs/path/to/repo/worktrees/task-01-system-settings",
  "branchName": "task-01-system-settings",
  "startedAt": "2025-12-30T22:06:23.200Z"
}
```

**Response 400 (если задача уже запущена):**
```json
{ "error": "Task already running" }
```

### Stop Task

```http
POST /api/tasks/:id/stop
```

**Request body:**
```json
{ "projectId": "my-project" }
```

**Response 200:**
```json
{ "taskId": "01-system-settings", "status": "Failed" }
```

### Next Stage

```http
POST /api/tasks/:id/next-stage
```

**Request body:**
```json
{ "projectId": "my-project" }
```

**Response 200:**
```json
{
  "taskId": "zz-stage-test",
  "stage": "Implementation",
  "status": "New"
}
```

### Task History

```http
GET /api/tasks/:id/history?projectId=:projectId
```

**Response 200:**
```json
{
  "history": [
    {
      "id": "run-1767132383200",
      "stage": "Verification",
      "status": "Failed",
      "startedAt": "2025-12-30T22:06:23.200Z",
      "completedAt": "2025-12-30T22:09:43.557Z",
      "duration": 200357,
      "model": {
        "agenticHarness": "opencode",
        "modelProvider": "opencode",
        "modelName": "claude-sonnet-4-5",
        "fullName": "opencode/claude-sonnet-4-5"
      },
      "logFile": "01-system-settings-verification-1767132383200.log"
    }
  ]
}
```

### List Task Logs (filenames)

```http
GET /api/projects/:projectId/tasks/:taskId/logs
```

**Response 200:**
```json
{
  "logs": [
    { "file": "01-system-settings-verification-1767132383200.log", "stage": "verification", "timestamp": 1767132383200 }
  ]
}
```

### Read Log File

```http
GET /api/projects/:projectId/logs/:logFile
```

**Response 200:** `text/plain` (контент лога).
