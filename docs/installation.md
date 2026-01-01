# Инструкция по установке NCrew

NCrew — UI + backend для управления задачами и запуска `opencode` в изолированных Git worktree.

## Требования

- **Node.js**: 18+
- **npm**: 9+
- **Git**: 2+
- **opencode CLI**: установлен и доступен в `PATH`

Проверка:

```bash
node --version
npm --version
git --version
opencode --help
```

## Установка

```bash
git clone <repository-url>
cd ncrew

npm install
cd backend && npm install && cd ..
cd frontend && npm install && cd ..
```

## Первый запуск: системные файлы `~/.ncrew`

При старте backend автоматически создаёт:

```
~/.ncrew/
  settings/
    projects/
    models-cache.json
  templates/
  stage_prompts/
```

## Подготовка проекта (где будут задачи)

Проект должен быть Git-репозиторием. Создайте папку задач:

```bash
mkdir -p /путь/к/проекту/.memory_bank/tasks
```

Логи запусков будут сохраняться в `/путь/к/проекту/.memory_bank/logs/`, а worktree — в `/путь/к/проекту/worktrees/`.

## Запуск

### Development

```bash
npm run dev
```

- Frontend: `http://localhost:3000` (если порт занят — Vite выберет следующий)
- Backend API: по умолчанию `http://localhost:3001` (если порт занят — `npm run dev` выберет следующий свободный и настроит proxy `/api` в Vite)

### Production (backend раздаёт `frontend/dist`)

```bash
npm -C frontend run build
node backend/server.js
```

Открыть: `http://localhost:3001`

## Troubleshooting

- `opencode` пишет файлы в домашнюю директорию (например, `~/.local/share/opencode/…`). Убедитесь, что процесс имеет права на запись.

### Настройка портов

Порты можно переопределять через переменные окружения:

- Backend: `PORT=3002 npm run backend` (или `PORT=3002 node backend/server.js`)
- Frontend proxy (Vite): `VITE_BACKEND_URL=http://localhost:3002 npm run frontend`

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

# Вариант 1: `npm run dev` сам подберёт свободный backend-порт
# Вариант 2: задать порт вручную
PORT=3002 npm run backend
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
# Vite обычно сам выберет следующий порт (если 3000 занят).
# Если нужен фиксированный порт:
VITE_PORT=3002 npm run frontend
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
