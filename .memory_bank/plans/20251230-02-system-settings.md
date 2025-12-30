# План реализации: System Settings (~/.ncrew)

**Основан на спецификации:** `.memory_bank/tasks/01-system-settings.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0

## Обзор

Перенос настроек из папки проекта в системную директорию `~/.ncrew` для кроссплатформенности и возможности поставки в виде бинарника/контейнера.

## Предварительные требования

### Текущее состояние проекта
- Backend: `backend/server.js`
- Frontend: React + Vite
- Настройки: `settings/` в корне проекта
- Кеш моделей: `settings/models-cache.json`
- Логи: не хранятся

### Зависимости
```json
{
  "dependencies": {
    "fs-extra": "^11.x"
  }
}
```

### Node.js встроенные модули
- `path` - уже используется
- `os` - нужен для `os.homedir()`

## Этап 1: Backend - Системные пути

### 1.1. Создать утилиты для системных путей

**Файл:** `backend/utils/paths.js`

**Задача:**
1. Функция `getNcrewHomeDir()` - возвращает `~/.ncrew` кроссплатформенно
2. Функция `getSettingsDir()` - возвращает `~/.ncrew/settings`
3. Функция `getProjectsDir()` - возвращает `~/.ncrew/settings/projects`
4. Функция `getTemplatesDir()` - возвращает `~/.ncrew/templates`
5. Функция `getStagePromptsDir()` - возвращает `~/.ncrew/stage_prompts`
6. Функция `getModelsCacheFile()` - возвращает `~/.ncrew/settings/models-cache.json`

**Псевдокод:**
```javascript
const os = require('os');
const path = require('path');
const fs = require('fs-extra');

function getNcrewHomeDir() {
  return path.join(os.homedir(), '.ncrew');
}

function getSettingsDir() {
  return path.join(getNcrewHomeDir(), 'settings');
}

function getProjectsDir() {
  return path.join(getSettingsDir(), 'projects');
}

// ... и т.д.
```

### 1.2. Функция инициализации структуры

**Файл:** `backend/utils/init.js`

**Задача:**
1. Создать функцию `initNcrewStructure()`
2. При запуске backend:
   - Проверить существование `~/.ncrew/`
   - Создать структуру папок если не существует
   - Создать пустой `models-cache.json` если не существует
3. Обработка ошибок (нет прав на запись)

**Псевдокод:**
```javascript
async function initNcrewStructure() {
  const dirs = [
    getSettingsDir(),
    getProjectsDir(),
    getTemplatesDir(),
    getStagePromptsDir()
  ];

  for (const dir of dirs) {
    await fs.ensureDir(dir);
  }

  const cacheFile = getModelsCacheFile();
  if (!await fs.pathExists(cacheFile)) {
    await fs.writeJson(cacheFile, {});
  }
}
```

## Этап 2: Backend - Миграция настроек

### 2.1. Функция миграции из старого location

**Файл:** `backend/utils/migrate.js`

**Задача:**
1. Создать функцию `migrateOldSettings()`
2. Проверить существование старых настроек `backend/../settings/`
3. Если существуют:
   - Скопировать `projects/` в `~/.ncrew/settings/projects/`
   - Скопировать `models-cache.json` в `~/.ncrew/settings/models-cache.json`
   - Создать backup старых настроек `backend/../settings/backup/`
4. Вывести лог миграции

**Псевдокод:**
```javascript
async function migrateOldSettings() {
  const oldSettingsDir = path.join(__dirname, '../settings');
  const newSettingsDir = getSettingsDir();
  
  if (!await fs.pathExists(oldSettingsDir)) {
    console.log('No old settings to migrate');
    return;
  }
  
  // Migrate projects
  const oldProjectsDir = path.join(oldSettingsDir, 'projects');
  const newProjectsDir = getProjectsDir();
  await fs.copy(oldProjectsDir, newProjectsDir);
  
  // Migrate models cache
  const oldCacheFile = path.join(oldSettingsDir, 'models-cache.json');
  const newCacheFile = getModelsCacheFile();
  if (await fs.pathExists(oldCacheFile)) {
    await fs.copy(oldCacheFile, newCacheFile);
  }
  
  // Backup old settings
  const backupDir = path.join(oldSettingsDir, 'backup');
  await fs.copy(oldSettingsDir, backupDir);
}
```

## Этап 3: Backend - Обновление server.js

### 3.1. Заменить константы путей

**Файл:** `backend/server.js`

**Задача:**
1. Импортировать утилиты путей
2. Заменить:
   ```javascript
   // Было:
   const SETTINGS_DIR = path.join(__dirname, '../settings/projects');
   const MODELS_CACHE_FILE = path.join(__dirname, '../settings/models-cache.json');
   
   // Стало:
   const { getProjectsDir, getModelsCacheFile } = require('./utils/paths');
   const SETTINGS_DIR = getProjectsDir();
   const MODELS_CACHE_FILE = getModelsCacheFile();
   ```

### 3.2. Вызвать инициализацию при старте

**Файл:** `backend/server.js`

**Задача:**
1. При запуске сервера вызвать `initNcrewStructure()`
2. Вызвать `migrateOldSettings()`
3. Обработка ошибок при инициализации

**Псевдокод:**
```javascript
const { initNcrewStructure } = require('./utils/init');
const { migrateOldSettings } = require('./utils/migrate');

// При старте
(async () => {
  try {
    await initNcrewStructure();
    await migrateOldSettings();
    console.log('NCrew structure initialized successfully');
  } catch (error) {
    console.error('Failed to initialize NCrew structure:', error);
  }
})();
```

## Этап 4: Backend - Логи в проекте

### 4.1. Обновить путь к логам

**Файл:** `backend/server.js`

**Задача:**
1. Добавить функцию `getTaskLogsDir(projectPath)` в `utils/paths.js`
2. Возвращает `path.join(projectPath, '.memory_bank/logs')`
3. В `server.js` использовать новую функцию вместо `settings/logs/`

**Псевдокод:**
```javascript
// utils/paths.js
function getTaskLogsDir(projectPath) {
  return path.join(projectPath, '.memory_bank/logs');
}

// server.js
const { getTaskLogsDir } = require('./utils/paths');

// Было:
const logsDir = path.join(__dirname, '../settings/logs');

// Стало:
const logsDir = getTaskLogsDir(config.path);
```

### 4.2. Создание папки logs для проекта

**Файл:** `backend/server.js`

**Задача:**
1. При запуске задачи создавать папку `.memory_bank/logs/` в проекте
2. Обработка ошибок (нет прав на запись)

**Псевдокод:**
```javascript
const projectLogsDir = getTaskLogsDir(config.path);
await fs.ensureDir(projectLogsDir);
```

## Этап 5: Обновление API endpoints

### 5.1. Проверка всех API endpoints

**Файл:** `backend/server.js`

**Задача:**
1. Проверить все endpoints, которые используют пути
2. Обновить использование `SETTINGS_DIR` и `MODELS_CACHE_FILE`
3. Убедиться, что нет хардкодов путей к `settings/`

**Endpoints для проверки:**
- `GET /api/projects` - использует `SETTINGS_DIR`
- `GET /api/projects/:projectId/tasks` - использует путь к проекту
- `POST /api/projects` - использует `SETTINGS_DIR`
- `PUT /api/tasks/:id/model` - использует путь к проекту
- `POST /api/tasks/:taskId/run` - использует путь к проекту и логи

## Этап 6: Тестирование

### 6.1. Ручное тестирование

**Сценарии:**

1. **Чистый запуск (без старых настроек)**
   - Удалить `~/.ncrew/` если существует
   - Запустить backend
   - Проверить, что создана структура папок
   - Проверить создание пустого `models-cache.json`

2. **Миграция настроек**
   - Запустить backend со старыми настройками в `settings/`
   - Проверить, что настройки скопированы в `~/.ncrew/`
   - Проверить, что создан backup в `settings/backup/`

3. **API endpoints**
   - Создать проект через API
   - Проверить, что конфиг сохранён в `~/.ncrew/settings/projects/`
   - Получить список проектов через API
   - Проверить, что список корректный

4. **Логи в проекте**
   - Запустить задачу (если реализовано)
   - Проверить, что логи сохранены в `.memory_bank/logs/` проекта
   - Проверить путь к логам

5. **Кроссплатформенность**
   - Тест на Unix/macOS
   - Тест на Windows (если возможно)

### 6.2. Проверка граничных случаев

1. Нет прав на запись в `~/.ncrew/`
2. `~/.ncrew/` уже существует с другой структурой
3. Старые настройки повреждены
4. Миграция interrupted (частично скопированы)

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend - системные пути)
2. Этап 2 (Backend - миграция)
3. Этап 3 (Backend - обновление server.js)
4. Этап 4 (Backend - логи в проекте)
5. Этап 5 (API endpoints)
6. Этап 6 (Тестирование)

### Приоритет:
1. Этап 1-5 - реализация
2. Этап 6 - тестирование

## Приемочные критерии

После реализации проверить:
- ✅ При запуске backend создаётся структура `~/.ncrew/`
- ✅ Структура включает `settings/`, `templates/`, `stage_prompts/`
- ✅ Существующие настройки мигрируются автоматически
- ✅ Пути вычисляются кроссплатформенно (Unix/macOS/Windows)
- ✅ API endpoints используют новые пути
- ✅ Логи сохраняются в `.memory_bank/logs/` проекта
- ✅ Создаётся backup старых настроек

## Примечания

1. **Кроссплатформенность:** Использовать `os.homedir()` для домашней директории
2. **Миграция:** Не удалять старые настройки, создавать backup
3. **Инициализация:** Выполнять при каждом запуске backend
4. **Логирование:** Добавить детальное логирование миграции
5. **Обработка ошибок:** Нельзя падать при ошибках миграции, продолжать работу

## Зависимости

### Требуется проверить:
```json
{
  "dependencies": {
    "fs-extra": "^11.x"
  }
}
```

### Node.js встроенные модули:
- `os` - новый модуль
- `path` - уже используется
- `fs` - заменён на `fs-extra`

## Время реализации

Оценка:
- Этап 1 (системные пути): 1 час
- Этап 2 (миграция): 1 час
- Этап 3 (обновление server.js): 1 час
- Этап 4 (логи в проекте): 30 мин
- Этап 5 (API endpoints): 30 мин
- Этап 6 (тестирование): 1 час

**Итого:** 4-5 часов
