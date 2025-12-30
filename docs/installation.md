# Инструкция по установке NCrew

Это руководство поможет вам установить и настроить NCrew на вашем компьютере.

## Системные требования

### Обязательно

- **Node.js**: версии 18.x или выше
- **Git**: версии 2.x или выше
- **npm**: версии 9.x или выше

### Дополнительно

- **opencode CLI**: Установлен и доступен в PATH
  - Установка: см. https://github.com/sst/opencode
- Git-репозиторий проекта, в котором будут выполняться задачи

### Проверка требований

```bash
# Проверка Node.js
node --version  # Должно быть >= 18

# Проверка npm
npm --version   # Должно быть >= 9

# Проверка Git
git --version   # Должно быть >= 2

# Проверка opencode
opencode --help # Должно показать справку
```

## Установка

### Шаг 1: Клонирование репозитория

```bash
git clone <repository-url>
cd ncrew
```

### Шаг 2: Установка зависимостей

Установите зависимости для всех частей проекта:

```bash
# Корневые зависимости
npm install

# Backend зависимости
cd backend
npm install
cd ..

# Frontend зависимости
cd frontend
npm install
cd ..
```

Или одной командой:

```bash
npm install && cd backend && npm install && cd ../frontend && npm install
```

## Настройка

### Шаг 1: Проверка структуры папок

Убедитесь, что структура папок выглядит так:

```
ncrew/
├── backend/
│   ├── node_modules/
│   ├── package.json
│   └── server.js
├── frontend/
│   ├── node_modules/
│   ├── package.json
│   └── src/
├── settings/
│   └── projects/
├── package.json
└── README.md
```

### Шаг 2: Создание папки для настроек

Папка `settings/projects/` создается автоматически при первом запуске, но можно создать её вручную:

```bash
mkdir -p settings/projects
```

### Шаг 3: Настройка проекта для задач

В вашем целевом проекте (где будут выполняться задачи) создайте папку для задач:

```bash
cd /путь/к/вашему/проекту
mkdir -p .memory_bank/tasks
```

## Запуск

### Режим разработки

Для разработки используйте concurrently для запуска backend и frontend:

```bash
npm run dev
```

Это запустит:
- Backend на http://localhost:3001
- Frontend на http://localhost:3000

### Отдельный запуск

Для более детального управления запускайте компоненты отдельно:

**Терминал 1 - Backend:**
```bash
npm run backend
```

**Терминал 2 - Frontend:**
```bash
npm run frontend
```

### Производственный режим

Для продакшена используйте следующие команды:

```bash
# Сборка frontend
cd frontend
npm run build

# Запуск backend (serving frontend)
cd ../backend
NODE_ENV=production node server.js
```

## Доступ к приложению

После запуска откройте браузер и перейдите по адресу:

```
http://localhost:3000
```

## Первичная настройка

### 1. Добавление проекта

1. Откройте http://localhost:3000
2. Нажмите кнопку "Add Project"
3. Заполните форму:
   - **Name**: Название проекта (например, "My App")
   - **Path**: Полный путь к папке проекта (например, `/home/dev/my-app`)
   - **Model**: Выберите модель AI (например, `claude-3.5-sonnet`)
   - **Provider**: Выберите провайдера (например, `anthropic`)
4. Нажмите "Save"

### 2. Проверка задач

Если в вашем проекте уже есть задачи в `.memory_bank/tasks/`, они отобразятся в интерфейсе.

Если нет, создайте первую задачу:

```bash
cd /путь/к/вашему/проекту/.memory_bank/tasks
cat > test-task.md << 'EOF'
---
title: Test task
status: New
priority: Low
---

Это тестовая задача для проверки работы NCrew.
EOF
```

Задача должна появиться в интерфейсе автоматически (благодаря file watching).

### 3. Запуск тестовой задачи

1. Найдите задачу "Test task" в списке
2. Нажмите кнопку "Run"
3. Наблюдайте за выполнением в разделе "Logs"

## Конфигурация

### Переменные окружения

Создайте файл `.env` в корне проекта:

```bash
# Backend
PORT=3001
NODE_ENV=development

# Frontend (для Vite)
VITE_API_URL=http://localhost:3001
```

### Настройка портов

Для изменения портов редактируйте соответствующие файлы:

**Backend порт:** `backend/server.js`
```javascript
const PORT = process.env.PORT || 3001;
```

**Frontend порт:** `frontend/vite.config.js`
```javascript
server: {
  port: 3000
}
```

## Проверка установки

### Проверка backend

```bash
curl http://localhost:3001/api/projects
```

Ожидаемый ответ:
```json
[]
```

или список проектов, если они уже добавлены.

### Проверка frontend

Откройте http://localhost:3000 в браузере. Вы должны увидеть интерфейс NCrew.

## Устранение проблем

### Backend не запускается

**Проблема:** Порт уже занят
```bash
# Проверьте, какой процесс использует порт
lsof -i :3001  # macOS/Linux
netstat -ano | findstr :3001  # Windows

# Измените порт в backend/server.js
```

**Проблема:** Module not found
```bash
# Переустановите зависимости backend
cd backend
rm -rf node_modules package-lock.json
npm install
```

### Frontend не запускается

**Проблема:** Порт уже занят
```bash
# Измените порт в frontend/vite.config.js
```

**Проблема:** Module not found
```bash
# Переустановите зависимости frontend
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Задачи не появляются

**Проблема:** Путь к проекту указан неверно
- Проверьте, что путь абсолютный (начинается с `/` или `C:\`)
- Убедитесь, что папка существует

**Проблема:** Папка .memory_bank/tasks не существует
```bash
# Создайте папку задач
mkdir -p /путь/к/проекту/.memory_bank/tasks
```

### opencode не найден

**Проблема:** opencode не установлен или не в PATH
```bash
# Проверьте установку
which opencode  # macOS/Linux
where opencode   # Windows

# Если не найден, установите
npm install -g @sst/opencode
```

## Обновление

Для обновления до последей версии:

```bash
git pull origin main
npm install
cd backend && npm install
cd ../frontend && npm install
```

## Удаление

Для полного удаления:

```bash
# Остановите процессы (Ctrl+C)
# Удалите папку проекта
rm -rf ncrew

# (Опционально) Удалите глобальные зависимости
npm uninstall -g @sst/opencode
```

## Дополнительные ресурсы

- [Руководство пользователя](user-guide.md)
- [Архитектура](architecture.md)
- [Руководство для разработчиков](development.md)
- [API Reference](api.md)
