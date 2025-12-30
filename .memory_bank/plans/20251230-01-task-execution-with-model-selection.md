# План реализации: Выполнение задачи с выбором модели

**Основан на спецификации:** `.memory_bank/specs/20251230-01-task-execution-with-model-selection.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0

## Обзор

План описывает реализацию функционала для запуска задач через AI-агента с выбором модели. Включает хранение кеша моделей, UI для выбора, обновление фронтматтера, выполнение команды opencode.

## Предварительные требования

### Текущее состояние проекта
- Backend: Express.js в одном файле `backend/server.js`
- Frontend: React + Vite, polling каждые 5 сек для обновления задач
- Хранение: JSON файлы в `settings/projects/`
- Парсинг: Функция `parseFrontmatter` в `server.js`

### Зависимости (необходимо проверить)
- `fs-extra` - используется
- `child_process` - нужен для выполнения `opencode models` и запуска задач

## Этап 1: Backend - Сервис моделей

### 1.1. Получение списка моделей

**Файл:** `backend/server.js`

**Задача:**
1. Добавить функцию `fetchModels()` для выполнения команды `opencode models`
2. Парсить вывод команды
3. Форматировать в массив объектов:
   ```javascript
   {
     provider: "opencode",
     name: "claude-sonnet-4-5",
     fullName: "opencode/claude-sonnet-4-5"
   }
   ```
4. Группировать по провайдеру для удобства использования

**Псевдокод:**
```javascript
async function fetchModels() {
  const { stdout } = await exec('opencode models');
  const lines = stdout.trim().split('\n');
  return lines.map(line => {
    const [provider, name] = line.split('/');
    return { provider, name, fullName: line };
  });
}
```

### 1.2. Кеширование списка моделей

**Файл:** `backend/server.js`

**Задача:**
1. Создать путь `settings/models-cache.json`
2. Функция `loadCachedModels()` - читает кеш из файла
3. Функция `saveCachedModels(models)` - сохраняет кеш с timestamps:
   ```json
   {
     "models": [...],
     "cachedAt": "2025-12-30T10:00:00Z",
     "expiresAt": "2025-12-31T10:00:00Z"
   }
   ```
4. Функция `getModels()` - возвращает кеш или обновляет, если устарел (>24 часа)

**Логика:**
- При старте сервера: загрузить кеш
- При запросе `/api/models`: проверить срок годности
  - Если актуален - вернуть из кеша
  - Если устарел - обновить и вернуть

### 1.3. API endpoint для получения моделей

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `GET /api/models`
2. Вызывать `getModels()`
3. Обрабатывать ошибки:
   - `opencode not found in PATH` → 503
   - Other errors → 500

### 1.4. API endpoint для принудительного обновления

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `POST /api/models/refresh`
2. Вызывать `fetchModels()` принудительно
3. Обновить кеш
4. Вернуть обновлённый список

### 1.5. Валидация дефолтной модели

**Файл:** `backend/server.js`

**Задача:**
1. В `POST /api/projects` - проверить, что выбранная модель существует
2. Получить список моделей через `getModels()`
3. Проверить, что `defaultModel.fullName` есть в списке
4. Если нет → 400 Bad Request

## Этап 2: Backend - Обновление задач

### 2.1. Обновить парсинг фронтматтера

**Файл:** `backend/server.js`

**Задача:**
1. Обновить функцию `parseFrontmatter()` для извлечения новых полей:
   - `agenticHarness` (default: "opencode")
   - `modelProvider` (default: из проекта)
   - `modelName` (default: из проекта)
2. Если поля отсутствуют - вернуть null или объект с defaults

### 2.2. Добавить модель в ответ задачи

**Файл:** `backend/server.js`

**Задача:**
1. В `GET /api/projects/:projectId/tasks` добавить в объект задачи:
   ```javascript
   {
     id: taskId,
     title,
     status,
     priority,
     model: {
       agenticHarness: "opencode",
       modelProvider: "opencode",
       modelName: "claude-sonnet-4-5"
     }
   }
   ```
2. Если модель не указана во фронтматтере - использовать дефолтную из проекта

### 2.3. API endpoint для обновления модели задачи

**Файл:** `backend/server.js`

**Задача:**
1. Добавить `PUT /api/tasks/:id/model`
2. Request body: `{ model: { agenticHarness, modelProvider, modelName } }`
3. Прочитать файл задачи
4. Обновить фронтматтер (вставить/обновить поля)
5. Записать обратно в файл
6. Вернуть обновлённую задачу

**Логика обновления фронтматтера:**
- Если есть фронтматтер → обновить поля
- Если нет → добавить фронтматтер с полями

## Этап 3: Backend - Запуск задачи

### 3.1. Создание Git Worktree

**Файл:** `backend/server.js`

**Задача:**
1. Добавить функцию `createWorktree(projectPath, taskId, worktreePrefix)`
2. Вычислить имя ветки: `${worktreePrefix}${taskId}`
3. Путь к worktree: `path.join(projectPath, 'worktrees', branchName)`
4. Выполнить команду:
   ```bash
   git worktree add <worktree-path> -b <branch-name>
   ```
5. Обрабатывать ошибки

### 3.2. Запуск процесса opencode

**Файл:** `backend/server.js`

**Задача:**
1. Обновить `POST /api/tasks/:taskId/run`
2. Получить модель из request body или из задачи
3. Вычислить путь к файлу задачи от корня проекта: `.memory_bank/tasks/${taskId}.md`
4. Сформировать команду:
   ```bash
   opencode -m <provider>/<name> run "прочитай и выполни задачу из файла .memory_bank/tasks/<taskId>.md"
   ```
5. Запустить subprocess в папке worktree
6. Обновить статус задачи на "Running" во фронтматтере
7. Записать лог в начало: `[NCrew] Using model: <provider>/<name>`

**Псевдокод:**
```javascript
const { modelProvider, modelName } = model;
const command = `opencode -m ${modelProvider}/${modelName} run "прочитай и выполни задачу из файла .memory_bank/tasks/${taskId}.md"`;

const process = spawn('opencode', ['-m', `${modelProvider}/${modelName}`, 'run', `прочитай и выполни задачу из файла .memory_bank/tasks/${taskId}.md`], {
  cwd: worktreePath
});
```

### 3.3. Мониторинг процесса

**Файл:** `backend/server.js`

**Задача:**
1. Захватывать stdout/stderr процесса
2. Сохранять логи в отдельный файл: `settings/logs/${taskId}-${timestamp}.log`
3. По завершении (exit code):
   - Обновить статус на "Done" или "Failed" во фронтматтере
   - Записать exit code в лог
4. Хранить список запущенных процессов в памяти для возможной остановки

## Этап 4: Frontend - Компоненты

### 4.1. API service для моделей

**Файл:** Создать `frontend/src/services/models.js`

**Задача:**
1. `fetchModels()` - GET `/api/models`
2. `refreshModels()` - POST `/api/models/refresh`
3. Обрабатывать ошибки

### 4.2. Компонент ModelSelector

**Файл:** Создать `frontend/src/components/ModelSelector.jsx`

**Задача:**
1. Пропсы: `models`, `selectedModel`, `onSelect`
2. Dropdown с поиском
3. Сгруппированы по провайдеру:
   ```
   ▼ opencode
     claude-sonnet-4-5
     claude-opus-4-5
   ```
4. Отображать выбранную модель

### 4.3. Добавить выбор модели в карточку задачи

**Файл:** `frontend/src/components/ProjectView.jsx` (функция TaskCard)

**Задача:**
1. Добавить `ModelSelector` в карточку
2. При выборе модели → вызывать API `/api/tasks/:id/model`
3. Обновлять состояние задачи

### 4.4. Модалка для выбора модели при запуске

**Файл:** Создать `frontend/src/components/RunTaskModal.jsx`

**Задача:**
1. Props: `task`, `model`, `onRun`, `onCancel`
2. Показывать текущую модель
3. `ModelSelector` для изменения
4. Кнопки "Run" и "Cancel"

### 4.5. Обновить запуск задачи в ProjectView

**Файл:** `frontend/src/components/ProjectView.jsx`

**Задача:**
1. При клике "Run" → открыть модалку вместо прямого запуска
2. В модалке можно выбрать модель
3. При подтверждении → вызывать `/api/tasks/:taskId/run` с моделью

### 4.6. Кнопка Refresh models

**Файл:** `frontend/src/App.jsx` или `ProjectView.jsx`

**Задача:**
1. Добавить кнопку "Refresh models" в UI
2. При нажатии → вызывать `refreshModels()`
3. Обновлять список моделей

## Этап 5: Интеграция и полировка

### 5.1. Обновить конфигурацию проекта

**Файл:** `frontend/src/App.jsx` (форма добавления проекта)

**Задача:**
1. Добавить `ModelSelector` в форму добавления проекта
2. Сохранять `defaultModel` в конфиг
3. Валидация при сохранении

### 5.2. Загрузить модели при старте

**Файл:** `frontend/src/App.jsx`

**Задача:**
1. Загружать модели при старте приложения
2. Сохранять в state для использования во всем приложении
3. Обрабатывать ошибки (если opencode не установлен)

### 5.3. Обновить логирование

**Файл:** `backend/server.js`

**Задача:**
1. Добавить детальное логирование:
   - `fetchModels()`: время выполнения
   - `createWorktree()`: путь к worktree
   - Запуск процесса: команда, pid
   - Завершение: exit code, время выполнения

### 5.4. Обработка ошибок

**Файл:** `backend/server.js`

**Задача:**
1. Обработка ошибок для всех новых endpoints
2. Возврат понятных сообщений
3. Логирование ошибок с контекстом

## Этап 6: Тестирование

### 6.1. Ручное тестирование

**Сценарии:**
1. Создать проект, выбрать дефолтную модель
2. Создать задачу с моделью во фронтматтере
3. Запустить задачу - проверить работу worktree
4. Проверить логи
5. Изменить модель задачи и перезапустить
6. Refresh models - проверка кеширования

### 6.2. Проверка граничных случаев

1. opencode не установлен
2. Недоступная модель
3. Работа с существующими задачами (без полей модели)
4. Несколько задач параллельно
5. Путь проекта с пробелами/спецсимволами

## Порядок выполнения

### Параллельные задачи (можно делать одновременно):
- Этап 1.1 - 1.4 (Backend: модели)
- Этап 4.1 - 4.2 (Frontend: ModelSelector)

### Последовательные задачи:
1. Этап 1 → Этап 2 → Этап 3 (Backend)
2. Этап 4 → Этап 5 → Этап 6 (Frontend + Интеграция)

### Приоритет:
1. Backend (Этапы 1-3) - основная функциональность
2. Frontend (Этап 4) - UI
3. Интеграция (Этап 5) - связка
4. Тестирование (Этап 6) - проверка

## Приемочные критерии

После реализации проверить:
- ✅ `GET /api/models` возвращает список моделей
- ✅ Кеш работает (24 часа)
- ✅ `POST /api/models/refresh` обновляет список
- ✅ Дефолтная модель сохраняется в конфиг проекта
- ✅ Модель задачи отображается в UI
- ✅ Модель задачи сохраняется во фронтматтере
- ✅ `POST /api/tasks/:taskId/run` запускает задачу с выбранной моделью
- ✅ Worktree создаётся правильно
- ✅ Логи содержат информацию о модели
- ✅ Ошибки обрабатываются корректно

## Примечания

1. **Парсинг фронтматтера:** Использовать существующий подход с regex, расширить для новых полей
2. **Git команды:** Использовать `child_process.exec` или `spawn`
3. **Кеш:** Сохранять в `settings/models-cache.json`
4. **Логи:** Сохранять в `settings/logs/`
5. **Polling:** Продолжить использовать polling для обновления статусов (5 сек)
6. **React state:** Поднимать состояние моделей в `App.jsx` для глобального доступа

## Зависимости

### Требуется проверить:
```json
{
  "dependencies": {
    "fs-extra": "^11.x"
  },
  "devDependencies": {
    "concurrently": "^8.x"
  }
}
```

### Node.js встроенные модули:
- `child_process` - для выполнения команд
- `path` - уже используется
- `fs` - заменён на `fs-extra`

## Время реализации

Оценка:
- Этап 1 (Backend модели): 2-3 часа
- Этап 2 (Backend задачи): 1-2 часа
- Этап 3 (Backend запуск): 2-3 часа
- Этап 4 (Frontend): 2-3 часа
- Этап 5 (Интеграция): 1-2 часа
- Этап 6 (Тестирование): 1-2 часа

**Итого:** 9-15 часов
