# Многопроектная архитектура NeuroCrew Lab

## Обзор

NeuroCrew Lab теперь поддерживает **многопроектную архитектуру** с хранением конфигурации в `~/.ncrew/`.

### Основные изменения

1. **Конфигурация проектов хранится в ~/.ncrew/**
   - Каждый проект имеет изолированную конфигурацию
   - Отдельные .env файлы для каждого проекта
   - Независимые роли и промпты

2. **CLI для управления проектами**
   - Создание, переключение, удаление проектов
   - Просмотр текущего проекта

3. **UI с боковой панелью**
   - Отображение списка проектов
   - Переключение между проектами
   - Навигация по настройкам

## Структура директорий

```
~/.ncrew/
├── current_project.txt          # Имя текущего проекта
├── ncrew/                        # Проект "ncrew"
│   ├── .env                      # Конфигурация проекта
│   ├── roles/
│   │   └── agents.yaml           # Роли агентов
│   ├── prompts/                  # Промпты агентов
│   └── data/
│       └── conversations/        # История диалогов
├── test_yaml_new/                # Проект "test_yaml_new"
│   ├── .env
│   ├── roles/
│   │   └── agents.yaml
│   └── data/
└── test_project/                 # Проект "test_project"
    ├── .env
    ├── roles/
    │   └── agents.yaml
    └── data/
```

## Использование CLI

### Создание проекта

```bash
python ncrew_cli.py init <project_name>
```

Создаёт новую структуру проекта в `~/.ncrew/<project_name>/`.

### Список проектов

```bash
python ncrew_cli.py list
```

Отображает все доступные проекты и текущий активный.

### Переключение проекта

```bash
python ncrew_cli.py switch <project_name>
```

Переключается на указанный проект.

### Текущий проект

```bash
python ncrew_cli.py current
```

Показывает информацию о текущем активном проекте.

### Удаление проекта

```bash
python ncrew_cli.py delete <project_name>
```

Удаляет проект (требует подтверждения).

## Конфигурация проекта

Каждый проект имеет свой `.env` файл:

```bash
# ~/.ncrew/<project_name>/.env

MAIN_BOT_TOKEN=your_main_bot_token_here
TARGET_CHAT_ID=your_chat_id_here
LOG_LEVEL=INFO
MAX_CONVERSATION_LENGTH=200
AGENT_TIMEOUT=600

# Токены для каждой роли
SOFTWARE_DEV_BOT_TOKEN=bot_token_1
CODE_REVIEW_BOT_TOKEN=bot_token_2
# ... и т.д.
```

## Роли проекта

Каждый проект имеет свой файл ролей:

```yaml
# ~/.ncrew/<project_name>/roles/agents.yaml

roles:
  - role_name: software_developer
    display_name: Software Developer
    telegram_bot_name: Software_Dev_Bot
    system_prompt_file: roles/prompts/software_developer.md
    agent_type: gemini_acp
    cli_command: gemini --experimental-acp
    description: "Разработчик на Rust/TypeScript/JavaScript"
    is_moderator: false
```

## API для программного управления

```python
from app.config_manager import multi_project_manager

# Создание проекта
project = multi_project_manager.create_project("my_project")

# Список проектов
projects = multi_project_manager.list_projects()

# Получение текущего проекта
current = multi_project_manager.get_current_project()

# Переключение проекта
multi_project_manager.set_current_project("my_project")

# Загрузка конфигурации проекта
config = multi_project_manager.load_project_config("my_project")
```

## Интеграция с main.py

При запуске `main.py`:

1. Автоматически определяется текущий проект из `~/.ncrew/current_project.txt`
2. Загружается конфигурация проекта из `~/.ncrew/<project>/`
3. Применяются переменные окружения из `.env` проекта
4. Загружаются роли из `roles/agents.yaml` проекта

Если проектов нет, создаётся проект по умолчанию "default".

## Web UI с многопроектностью

Файл `templates/projects_sidebar_ui.html` демонстрирует интерфейс с:

- Боковой панелью с списком проектов
- Возможностью переключения проектов
- Кнопками "Глобальные настройки" и "Настройка ролей" внизу панели (без заголовка "Быстрые действия")

## Миграция существующих проектов

Если у вас уже есть конфигурация в репозитории:

1. Создайте проект: `python ncrew_cli.py init my_existing_project`
2. Скопируйте `.env` в `~/.ncrew/my_existing_project/.env`
3. Скопируйте `roles/agents.yaml` в `~/.ncrew/my_existing_project/roles/agents.yaml`
4. Скопируйте промпты в `~/.ncrew/my_existing_project/prompts/`

## Переменные окружения

- `NCREW_PROJECT` - имя текущего проекта (устанавливается автоматически)
- `NCREW_PROJECT_ROOT` - путь к директории проекта

## Преимущества

1. **Изоляция** - каждый проект полностью независим
2. **Безопасность** - конфигурация вне репозитория
3. **Гибкость** - легко переключаться между проектами
4. **Масштабируемость** - неограниченное количество проектов
5. **Удобство** - не нужно редактировать файлы в репозитории

## Обратная совместимость

Система поддерживает старый формат с `.env` в корне репозитория:

- Если есть `~/.ncrew/`, используется многопроектная архитектура
- Если нет, fallback на `.env` в репозитории

Оба формата могут сосуществовать: project `.env` имеет приоритет, но можно дополнять переменными из репозиторного `.env`.
