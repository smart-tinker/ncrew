# API Reference NCrew

Документация по API endpoints NCrew.

## Базовый URL

```
http://localhost:3001/api
```

## Authentication

В текущей версии MVP аутентификация не реализована.

В будущих версиях будет добавлена JWT-аутентификация.

## Errors

Коды ответов:

- `200 OK` - Успешный запрос
- `201 Created` - Ресурс создан
- `400 Bad Request` - Неверные данные запроса
- `404 Not Found` - Ресурс не найден
- `500 Internal Server Error` - Ошибка сервера

Формат ошибки:

```json
{
  "error": "Error message",
  "details": {
    "field": "Additional details"
  }
}
```

## Endpoints

### Projects

#### Get All Projects

Получить список всех проектов.

```http
GET /api/projects
```

**Response 200:**
```json
[
  {
    "id": "proj-123",
    "name": "My App",
    "path": "/home/dev/my-app",
    "model": "claude-3.5-sonnet",
    "provider": "anthropic",
    "createdAt": "2025-01-15T10:00:00Z"
  }
]
```

#### Get Project by ID

Получить информацию о проекте.

```http
GET /api/projects/:id
```

**Parameters:**
- `id` (string, required) - ID проекта

**Response 200:**
```json
{
  "id": "proj-123",
  "name": "My App",
  "path": "/home/dev/my-app",
  "model": "claude-3.5-sonnet",
  "provider": "anthropic",
  "createdAt": "2025-01-15T10:00:00Z"
}
```

**Response 404:**
```json
{
  "error": "Project not found"
}
```

#### Create Project

Создать новый проект.

```http
POST /api/projects
```

**Request Body:**
```json
{
  "name": "My App",
  "path": "/home/dev/my-app",
  "model": "claude-3.5-sonnet",
  "provider": "anthropic",
  "opencodeArgs": ["--agent", "build"]
}
```

**Parameters:**
- `name` (string, required) - Название проекта
- `path` (string, required) - Абсолютный путь к проекту
- `model` (string, optional) - Модель AI (default: "claude-3.5-sonnet")
- `provider` (string, optional) - Провайдер AI (default: "anthropic")
- `opencodeArgs` (array, optional) - Дополнительные аргументы для opencode

**Response 201:**
```json
{
  "id": "proj-123",
  "name": "My App",
  "path": "/home/dev/my-app",
  "model": "claude-3.5-sonnet",
  "provider": "anthropic",
  "createdAt": "2025-01-15T10:00:00Z"
}
```

**Response 400:**
```json
{
  "error": "Invalid path",
  "details": {
    "path": "Path does not exist"
  }
}
```

#### Update Project

Обновить информацию о проекте.

```http
PUT /api/projects/:id
```

**Parameters:**
- `id` (string, required) - ID проекта

**Request Body:**
```json
{
  "name": "My App Updated",
  "model": "gpt-4o",
  "provider": "openai"
}
```

**Response 200:**
```json
{
  "id": "proj-123",
  "name": "My App Updated",
  "path": "/home/dev/my-app",
  "model": "gpt-4o",
  "provider": "openai",
  "createdAt": "2025-01-15T10:00:00Z"
}
```

#### Delete Project

Удалить проект.

```http
DELETE /api/projects/:id
```

**Parameters:**
- `id` (string, required) - ID проекта

**Response 200:**
```json
{
  "message": "Project deleted successfully"
}
```

#### Get Project Tasks

Получить все задачи проекта.

```http
GET /api/projects/:id/tasks
```

**Parameters:**
- `id` (string, required) - ID проекта

**Response 200:**
```json
[
  {
    "id": "task-456",
    "projectId": "proj-123",
    "title": "Add authentication",
    "status": "New",
    "priority": "High",
    "description": "Task description...",
    "filePath": "/home/dev/my-app/.memory_bank/tasks/auth.md",
    "logs": [],
    "exitCode": null,
    "startedAt": null,
    "completedAt": null
  }
]
```

---

### Tasks

#### Get All Tasks

Получить все задачи из всех проектов.

```http
GET /api/tasks
```

**Query Parameters:**
- `status` (string, optional) - Фильтр по статусу (New, In Progress, Done, Failed)
- `priority` (string, optional) - Фильтр по приоритету (Low, Medium, High)
- `projectId` (string, optional) - Фильтр по ID проекта

**Пример:**
```
GET /api/tasks?status=New&priority=High
```

**Response 200:**
```json
[
  {
    "id": "task-456",
    "projectId": "proj-123",
    "title": "Add authentication",
    "status": "New",
    "priority": "High",
    "description": "Task description...",
    "filePath": "/home/dev/my-app/.memory_bank/tasks/auth.md",
    "logs": [],
    "exitCode": null,
    "startedAt": null,
    "completedAt": null
  }
]
```

#### Get Task by ID

Получить детальную информацию о задаче.

```http
GET /api/tasks/:id
```

**Parameters:**
- `id` (string, required) - ID задачи

**Response 200:**
```json
{
  "id": "task-456",
  "projectId": "proj-123",
  "title": "Add authentication",
  "status": "In Progress",
  "priority": "High",
  "description": "Task description...",
  "filePath": "/home/dev/my-app/.memory_bank/tasks/auth.md",
  "logs": [
    "Starting task execution...",
    "Creating worktree...",
    "Running opencode..."
  ],
  "exitCode": null,
  "startedAt": "2025-01-15T10:30:00Z",
  "completedAt": null
}
```

**Response 404:**
```json
{
  "error": "Task not found"
}
```

#### Run Task

Запустить выполнение задачи.

```http
POST /api/tasks/run
```

**Request Body:**
```json
{
  "taskId": "task-456"
}
```

или для нескольких задач:

```json
{
  "taskIds": ["task-456", "task-789"]
}
```

**Parameters:**
- `taskId` (string, required) - ID одной задачи
- `taskIds` (array, optional) - Массив ID задач для множественного запуска

**Response 200:**
```json
{
  "message": "Tasks started successfully",
  "tasks": [
    {
      "id": "task-456",
      "status": "Running",
      "startedAt": "2025-01-15T10:30:00Z"
    },
    {
      "id": "task-789",
      "status": "Running",
      "startedAt": "2025-01-15T10:30:01Z"
    }
  ]
}
```

**Response 400:**
```json
{
  "error": "Task is already running"
}
```

#### Stop Task

Остановить выполнение задачи.

```http
POST /api/tasks/stop
```

**Request Body:**
```json
{
  "taskId": "task-456"
}
```

**Parameters:**
- `taskId` (string, required) - ID задачи

**Response 200:**
```json
{
  "message": "Task stopped successfully",
  "task": {
    "id": "task-456",
    "status": "Failed",
    "completedAt": "2025-01-15T10:35:00Z"
  }
}
```

#### Get Task Logs

Получить логи выполнения задачи.

```http
GET /api/tasks/:id/logs
```

**Parameters:**
- `id` (string, required) - ID задачи

**Query Parameters:**
- `limit` (number, optional) - Количество строк лога (default: all)
- `offset` (number, optional) - Смещение (default: 0)

**Пример:**
```
GET /api/tasks/task-456/logs?limit=100&offset=0
```

**Response 200:**
```json
{
  "logs": [
    "Starting task execution...",
    "Creating worktree...",
    "Running opencode...",
    "Reading files...",
    "Writing changes..."
  ],
  "total": 100,
  "offset": 0
}
```

---

## WebSocket API

### Connection

```javascript
const ws = new WebSocket('ws://localhost:3001/ws');
```

### Events

#### tasks.updated

Отправляется при изменении списка задач.

**Payload:**
```json
{
  "type": "tasks.updated",
  "data": [
    {
      "id": "task-456",
      "projectId": "proj-123",
      "title": "Add authentication",
      "status": "Done",
      "priority": "High"
    }
  ]
}
```

#### task.started

Отправляется при запуске задачи.

**Payload:**
```json
{
  "type": "task.started",
  "data": {
    "id": "task-456",
    "status": "Running",
    "startedAt": "2025-01-15T10:30:00Z"
  }
}
```

#### task.log

Отправляется при появлении новых логов.

**Payload:**
```json
{
  "type": "task.log",
  "data": {
    "taskId": "task-456",
    "log": "Reading files...",
    "timestamp": "2025-01-15T10:30:05Z"
  }
}
```

#### task.completed

Отправляется при завершении задачи.

**Payload:**
```json
{
  "type": "task.completed",
  "data": {
    "id": "task-456",
    "status": "Done",
    "exitCode": 0,
    "completedAt": "2025-01-15T10:35:00Z"
  }
}
```

#### task.failed

Отправляется при ошибке выполнения задачи.

**Payload:**
```json
{
  "type": "task.failed",
  "data": {
    "id": "task-456",
    "status": "Failed",
    "exitCode": 1,
    "completedAt": "2025-01-15T10:35:00Z",
    "error": "Process timeout"
  }
}
```

### JavaScript Example

```javascript
const ws = new WebSocket('ws://localhost:3001/ws');

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch (message.type) {
    case 'tasks.updated':
      console.log('Tasks updated:', message.data);
      break;
    case 'task.started':
      console.log('Task started:', message.data);
      break;
    case 'task.log':
      console.log('Task log:', message.data.log);
      break;
    case 'task.completed':
      console.log('Task completed:', message.data);
      break;
    case 'task.failed':
      console.error('Task failed:', message.data);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket disconnected');
};
```

## Rate Limiting

В текущей версии MVP rate limiting не реализован.

В будущих версиях будет добавлено:
- Лимит запросов в минуту
- Лимит одновременных задач на пользователя

## Rate Limiting Headers

Когда rate limiting будет реализован, будут доступны заголовки:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1234567890
```

## CORS

В настройках разработки CORS разрешен для всех origins (`*`).

Для продакшена настройте whitelist:

```javascript
const allowedOrigins = [
  'https://yourdomain.com'
];

app.use(cors({
  origin: allowedOrigins
}));
```

## Versioning

Текущая версия API: `v1`

Версия указана в URL:

```
http://localhost:3001/api/v1/projects
```

## Changelog

### v1.0.0 (2025-01-15)

- Initial API release
- Projects CRUD operations
- Tasks CRUD operations
- Task execution
- WebSocket real-time updates

## Support

Если у вас есть вопросы по API, создайте issue в репозитории проекта.
