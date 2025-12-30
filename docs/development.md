# Руководство для разработчиков NCrew

Это руководство предназначено для разработчиков, которые хотят вносить вклад в развитие NCrew.

## Содержание

1. [Начало работы](#начало-работы)
2. [Структура проекта](#структура-проекта)
3. [Локальная разработка](#локальная-разработка)
4. [Тестирование](#тестирование)
5. [Контрибьюция](#контрибьюция)
6. [Код стиль](#код-стиль)

## Начало работы

### Требования

- Node.js 18+
- Git 2.x+
- npm 9+

### Клонирование и установка

```bash
git clone <repository-url>
cd ncrew
npm install
cd backend && npm install && cd ../frontend && npm install
```

### Запуск в режиме разработки

```bash
npm run dev
```

## Структура проекта

```
ncrew/
├── backend/                 # Backend (Express.js)
│   ├── routes/             # API routes
│   │   ├── projects.js     # Projects management
│   │   └── tasks.js        # Tasks management
│   ├── services/           # Business logic
│   │   ├── gitService.js   # Git operations
│   │   ├── taskScanner.js  # Task file watching
│   │   └── agentRunner.js  # Agent process management
│   ├── middleware/         # Express middleware
│   ├── utils/              # Utility functions
│   ├── server.js           # Main server file
│   └── package.json
├── frontend/                # Frontend (React + Vite)
│   ├── src/
│   │   ├── components/     # React components
│   │   │   ├── ProjectList.jsx
│   │   │   ├── TaskList.jsx
│   │   │   ├── TaskCard.jsx
│   │   │   ├── LogViewer.jsx
│   │   │   └── ...
│   │   ├── hooks/          # Custom React hooks
│   │   │   ├── useTasks.js
│   │   │   ├── useProjects.js
│   │   │   └── ...
│   │   ├── services/       # API services
│   │   │   └── api.js
│   │   ├── utils/          # Utility functions
│   │   ├── App.jsx         # Main App component
│   │   └── main.jsx        # Entry point
│   ├── public/             # Static files
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── settings/                # Settings storage
│   └── projects/           # Project configurations (JSON)
├── docs/                    # Documentation
├── tests/                   # Test files
├── .gitignore
├── package.json
└── README.md
```

## Локальная разработка

### Запуск backend

```bash
cd backend
node server.js
# или
npm run start
```

Backend будет доступен на http://localhost:3001

### Запуск frontend

```bash
cd frontend
npm run dev
```

Frontend будет доступен на http://localhost:3000

### Параллельный запуск

```bash
npm run dev
```

### Hot reload

- **Frontend**: Vite автоматически перезагружает изменения
- **Backend**: Для hot reload можно использовать nodemon:

```bash
# Установите nodemon
npm install -D nodemon

# Используйте вместо node
nodemon server.js
```

### Отладка

**Frontend (Chrome DevTools):**
- Используйте breakpoints в source файлах
- React DevTools для inspecting components

**Backend:**
```bash
# Запуск с отладкой
node --inspect server.js
```

Затем подключитесь через Chrome DevTools: `chrome://inspect`

## Тестирование

### Unit Tests

```bash
# Backend tests
cd backend
npm test

# Frontend tests
cd frontend
npm test
```

### Integration Tests

```bash
npm run test:integration
```

### E2E Tests

```bash
npm run test:e2e
```

### Тестовое покрытие

```bash
npm run test:coverage
```

## Разработка новых функций

### Добавление нового API endpoint

1. **Создайте route в `backend/routes/`**

```javascript
// backend/routes/example.js
const express = require('express');
const router = express.Router();

router.get('/', async (req, res) => {
  try {
    const result = await someService.getData();
    res.json(result);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
```

2. **Подключите route в `backend/server.js`**

```javascript
const exampleRoutes = require('./routes/example');
app.use('/api/example', exampleRoutes);
```

3. **Добавьте API service во frontend**

```javascript
// frontend/src/services/api.js
export const getExampleData = async () => {
  const response = await fetch('/api/example');
  return response.json();
};
```

### Добавление нового компонента React

1. **Создайте компонент в `frontend/src/components/`**

```javascript
// frontend/src/components/Example.jsx
import React from 'react';

export const Example = ({ data }) => {
  return (
    <div className="example">
      {data.map(item => (
        <div key={item.id}>{item.name}</div>
      ))}
    </div>
  );
};
```

2. **Используйте компонент**

```javascript
import { Example } from './components/Example';

function App() {
  const [data, setData] = useState([]);
  
  return (
    <div>
      <Example data={data} />
    </div>
  );
}
```

### Добавление нового сервиса

1. **Создайте сервис в `backend/services/`**

```javascript
// backend/services/exampleService.js
class ExampleService {
  async getData() {
    // Реализация
  }
  
  async processData(data) {
    // Реализация
  }
}

module.exports = new ExampleService();
```

2. **Используйте сервис в route**

```javascript
const exampleService = require('../services/exampleService');

router.get('/', async (req, res) => {
  const data = await exampleService.getData();
  res.json(data);
});
```

## Код стиль

### JavaScript/React

- Используйте **camelCase** для переменных и функций
- Используйте **PascalCase** для компонентов и классов
- Используйте **UPPER_CASE** для констант
- Ставьте **semicolon** в конце строк
- Используйте **2 spaces** для отступов

**Пример:**
```javascript
const MAX_COUNT = 100;

function calculateTotal(items) {
  return items.reduce((sum, item) => sum + item.price, 0);
}

class UserProfile {
  constructor(name) {
    this.name = name;
  }
}
```

### ESLint

```bash
# Проверка кода
npm run lint

# Автофикс
npm run lint:fix
```

### Prettier

```bash
# Форматирование кода
npm run format
```

## Коммитирование

### Формат коммитов

Используйте Conventional Commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: Новая функциональность
- `fix`: Исправление бага
- `docs`: Изменение документации
- `style`: Форматирование кода
- `refactor`: Рефакторинг
- `test`: Добавление тестов
- `chore`: Обновление инструментов и т.д.

**Примеры:**
```
feat(backend): добавить API endpoint для проектов

- Добавлен GET /api/projects
- Добавлен POST /api/projects
- Добавлена валидация входных данных

Closes #123
```

```
fix(frontend): исправить баг с обновлением статуса задачи

Проблема была в useEffect dependency array
```

### Перед коммитом

```bash
# Запустите тесты
npm test

# Запустите линтер
npm run lint

# Запустите форматирование
npm run format

# Проверьте изменения
git diff
```

## Pull Request

### PR Checklist

- [ ] Код соответствует код стилю проекта
- [ ] Все тесты проходят (`npm test`)
- [ ] Добавлены тесты для новой функциональности
- [ ] Обновлена документация (при необходимости)
- [ ] Коммиты следуют формату Conventional Commits
- [ ] PR содержит описание изменений

### PR Title

Используйте тот же формат, что и для коммитов:

```
feat(backend): добавить поддержку множественных проектов
```

### PR Description

```markdown
## Что изменилось
- Краткое описание изменений

## Почему
- Причина изменений

## Как тестировать
- Шаги для тестирования

## Скриншоты (если применимо)
- Прикрепите скриншоты

## Связанные issues
Closes #123
```

## Отладка

### Backend логирование

```javascript
const logger = require('../utils/logger');

logger.info('Task started', { taskId });
logger.error('Task failed', { taskId, error });
```

### Frontend логирование

```javascript
console.log('Data loaded:', data);
console.error('Error fetching data:', error);
```

### Chrome DevTools

1. Откройте DevTools (F12)
2. Вкладка Console для логов
3. Вкладка Network для запросов
4. Вкладка Elements для inspecting DOM

### Postman/Insomnia

Для тестирования API используйте Postman или Insomnia:

- Импортируйте коллекцию из `docs/api-collection.json`
- Тестируйте endpoints локально

## Производительность

### Frontend

- Используйте `useMemo` для мемоизации вычислений
- Используйте `useCallback` для мемоизации функций
- Ленивая загрузка компонентов (`React.lazy`)
- Код сплиттинг (code splitting)

**Пример:**
```javascript
const LazyComponent = React.lazy(() => import('./LazyComponent'));
```

### Backend

- Используйте кеширование
- Оптимизируйте запросы к файловой системе
- Используйте connection pooling для БД (если будет)
- Логируйте медленные операции

## Безопасность

### Валидация входных данных

```javascript
const { body } = req;
if (!body.path) {
  return res.status(400).json({ error: 'Path is required' });
}

// Проверьте, что путь не содержит malicious characters
if (body.path.includes('..')) {
  return res.status(400).json({ error: 'Invalid path' });
}
```

### Sanitization

```javascript
const sanitize = require('sanitize-html');
const cleanPath = sanitize(userInput);
```

### Error Handling

```javascript
try {
  // Operation
} catch (error) {
  logger.error('Operation failed', { error });
  res.status(500).json({ 
    error: 'Internal server error',
    message: process.env.NODE_ENV === 'development' ? error.message : undefined
  });
}
```

## Ресурсы

### Документация

- [React Documentation](https://react.dev)
- [Express.js Documentation](https://expressjs.com)
- [Node.js Documentation](https://nodejs.org/docs)
- [Vite Documentation](https://vitejs.dev)

### Инструменты

- [ESLint](https://eslint.org)
- [Prettier](https://prettier.io)
- [Jest](https://jestjs.io)

## Вопросы?

Если у вас есть вопросы, создайте issue или обратитесь к maintainers проекта.

Спасибо за ваш вклад! 🚀
