# Архитектура NCrew

Этот документ описывает архитектуру системы NCrew и её компоненты.

## Обзор системы

NCrew состоит из трех основных компонентов:

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                        │
│              (React + Vite @ :3000)                 │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP/WebSocket
┌──────────────────▼──────────────────────────────────┐
│                     Backend                         │
│               (Express.js @ :3001)                  │
└──────┬─────────────────┬──────────────────┬─────────┘
       │                 │                  │
       │ Git Commands    │ File System      │ Subprocess
       │                 │                  │
       ▼                 ▼                  ▼
   Git Worktrees    Task Files          Opencode
```

## Компоненты

### 1. Frontend

**Технологии:**
- React 18
- Vite
- Tailwind CSS (или другой CSS framework)

**Ответственности:**
- Отображение списка проектов и задач
- Управление формами (добавление проекта, конфигурация)
- Отображение статусов и логов в реальном времени
- Управление UI для запуска задач

**Структура:**
```
frontend/
├── src/
│   ├── components/
│   │   ├── ProjectList.jsx      # Список проектов
│   │   ├── TaskList.jsx          # Список задач
│   │   ├── TaskCard.jsx          # Карточка задачи
│   │   └── LogViewer.jsx         # Просмотрщик логов
│   ├── App.jsx                   # Главный компонент
│   └── main.jsx                  # Точка входа
```

### 2. Backend

**Технологии:**
- Node.js
- Express.js
- Chokidar (file watching)
- node-pty (terminal emulation)

**Ответственности:**
- API endpoints
- Сканирование папок задач
- Управление Git Worktrees
- Запуск и мониторинг процессов `opencode`
- Трансляция логов через WebSocket

**Структура:**
```
backend/
├── routes/
│   ├── projects.js       # Управление проектами
│   └── tasks.js          # Управление задачами
├── services/
│   ├── gitService.js     # Работа с Git
│   ├── taskScanner.js    # Сканирование задач
│   └── agentRunner.js    # Запуск агентов
└── server.js             # Главный сервер
```

### 3. Task Scanner

**Функционал:**
- Мониторинг папки `.memory_bank/tasks/`
- Парсинг MD-файлов с frontmatter
- Извлечение метаданных (title, status, priority)
- Обновление списка задач при изменениях

**Алгоритм:**
```
1. При запуске: сканировать все файлы в .memory_bank/tasks/
2. Для каждого файла:
   - Прочитать содержимое
   - Извлечь frontmatter
   - Парсить метаданные
   - Сохранить в памяти
3. При изменении файлов (через Chokidar):
   - Пересканировать измененные файлы
   - Обновить состояние
   - Уведомить Frontend через WebSocket
```

### 4. Git Service

**Функционал:**
- Создание Git Worktrees
- Управление ветками
- Удаление Worktrees

**Операции:**
```javascript
// Создание worktree
git worktree add <worktree-path> <branch-name>

// Удаление worktree
git worktree remove <worktree-path>

// Список worktrees
git worktree list
```

### 5. Agent Runner

**Функционал:**
- Запуск subprocess `opencode`
- Захват stdout/stderr
- Управление процессом (запуск, остановка, статус)

**Процесс выполнения:**
```
1. Получить задачу из очереди
2. Создать Git Worktree
3. Сгенерировать имя ветки (feat/task-name)
4. Запустить subprocess:
   - cd <worktree-path>
   - opencode <task-description> <additional-args>
5. Захватывать вывод процесса
6. Транслировать логи через WebSocket
7. По завершении обновить статус задачи
```

## Бизнес-процессы

### Процесс А: Создание и обнаружение задач

```
Developer ──► Create MD-file ──► .memory_bank/tasks/
                      │
                      ▼
            TaskScanner (Chokidar)
                      │
                      ▼
            Parse frontmatter
                      │
                      ▼
            Update task list ──► Frontend (WebSocket)
```

### Процесс Б: Запуск агента

```
Frontend ──► POST /api/tasks/run ──► Backend
                         │
                         ▼
            GitService.createWorktree()
                         │
                         ▼
            AgentRunner.startProcess()
                         │
                         ▼
            subprocess.exec('opencode')
                         │
                         ▼
            Capture stdout/stderr ──► Frontend (WebSocket)
                         │
                         ▼
            Wait for completion
                         │
                         ▼
            Update task status
```

### Процесс В: Завершение и ревью

```
Agent Process ──► Exit code 0/1 ──► Backend
                          │
                          ▼
            Update task status (Done/Failed)
                          │
                          ▼
            Save logs to file
                          │
                          ▼
            Notify Frontend
                          │
                          ▼
            Developer ──► Review Worktree
                          │
                          ├─► Merge to main
                          └─► Delete worktree
```

## API

### Projects

```
GET    /api/projects           # Получить список проектов
POST   /api/projects           # Добавить проект
PUT    /api/projects/:id       # Обновить проект
DELETE /api/projects/:id       # Удалить проект
GET    /api/projects/:id/tasks # Получить задачи проекта
```

### Tasks

```
GET    /api/tasks              # Получить все задачи
GET    /api/tasks/:id          # Получить деталь задачи
POST   /api/tasks/run          # Запустить задачу
POST   /api/tasks/stop         # Остановить задачу
GET    /api/tasks/:id/logs     # Получить логи задачи
```

### WebSocket

```
WS /ws                        # Соединение для real-time updates

События:
- tasks.updated    # Обновление списка задач
- task.started     # Задача запущена
- task.log         # Новая строка лога
- task.completed   # Задача завершена
```

## Структура данных

### Project

```typescript
interface Project {
  id: string;
  name: string;
  path: string;
  model: string;          // claude-3.5-sonnet, gpt-4o, etc.
  provider: string;       // anthropic, openai, etc.
  createdAt: Date;
}
```

### Task

```typescript
interface Task {
  id: string;
  projectId: string;
  title: string;
  status: 'New' | 'In Progress' | 'Done' | 'Failed';
  priority: 'Low' | 'Medium' | 'High';
  description: string;
  filePath: string;
  logs: string[];
  exitCode: number | null;
  startedAt: Date | null;
  completedAt: Date | null;
}
```

### Worktree

```typescript
interface Worktree {
  branchName: string;
  path: string;
  taskId: string;
  createdAt: Date;
}
```

## Конфигурация

### Backend config

```javascript
{
  port: 3001,
  maxConcurrentTasks: 5,
  taskTimeout: 30 * 60 * 1000, // 30 минут
  logRetentionDays: 7
}
```

### Project config

Сохраняется в `settings/projects/<project-id>.json`:

```json
{
  "id": "proj-123",
  "name": "my-app",
  "path": "/home/dev/my-app",
  "model": "claude-3.5-sonnet",
  "provider": "anthropic",
  "opencodeArgs": [
    "--agent", "build",
    "--timeout", "30m"
  ]
}
```

## Безопасность

### Валидация путей

- Все пути к проектам валидируются
- Prevent directory traversal attacks
- Проверка существования папок

### Управление процессами

- Лимиты на количество одновременных процессов
- Таймауты для задач
- Корректная остановка процессов

### Изоляция

- Каждая задача в отдельном worktree
- Нет доступа к файлам других задач
- Отсутствие shared state между задачами

## Масштабирование

### Текущие ограничения (MVP)

- Максимум 5 параллельных задач
- Одиночный сервер
- Локальное выполнение только

### Потенциальные улучшения

- Очередь задач (Redis/Bull)
- Горизонтальное масштабирование (несколько backend серверов)
- Удаленное выполнение (SSH/Container)
- Персистентность (БД для задач и логов)

## Мониторинг и логирование

### Логи

- Application logs (console/file)
- Task execution logs (сохраняются для каждой задачи)
- Error logs (с стек-трейсами)

### Метрики

- Количество активных задач
- Среднее время выполнения
- Успешность (Success Rate)

## Тестирование

### Unit Tests

- Task Scanner: парсинг frontmatter
- Git Service: команды git
- Agent Runner: управление процессами

### Integration Tests

- API endpoints
- WebSocket события
- Полный цикл выполнения задачи

### E2E Tests

- Добавление проекта
- Создание задачи
- Запуск агента
- Проверка результата
