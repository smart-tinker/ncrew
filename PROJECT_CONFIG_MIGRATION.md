# Миграция на многопроектную систему с config.yaml

## Основные изменения

Система переведена на **простую многопроектную архитектуру** с центральным хранилищем `~/.ncrew/`.

### Было

```
project/
├── .env                      # Конфигурация в репозитории
├── roles/
│   ├── agents.yaml          # Роли с промптами
│   └── prompts/             # Файлы промптов
└── data/                    # Локальные данные
```

### Стало

```
~/.ncrew/
├── current_project.txt      # Имя текущего проекта
├── prompts/                 # Общие промпты для всех проектов
│   ├── software_developer.md
│   ├── code_review.md
│   └── ...
└── my_project/             # Проект
    ├── config.yaml         # Все настройки в одном файле
    └── data/               # Данные проекта
```

## Формат config.yaml

Вместо `.env` + `roles/agents.yaml` теперь один файл:

```yaml
main_bot_token: "your_token"
target_chat_id: 123456789
log_level: INFO

roles:
  - role_name: software_developer
    display_name: Software Developer
    telegram_bot_name: Software_Dev_Bot
    telegram_bot_token: "bot_token"           # Опционально
    prompt_file: software_developer.md        # Из ~/.ncrew/prompts/
    agent_type: gemini_acp
    cli_command: "gemini --experimental-acp"
    description: "Разработчик"
    is_moderator: false
```

## Преимущества

1. **Один файл** - вся конфигурация в `config.yaml`
2. **Общие промпты** - редактируются один раз для всех проектов
3. **Изоляция** - проекты независимы
4. **Безопасность** - конфигурация вне репозитория
5. **Простота** - MVP-подход, без сложностей

## Как начать

### 1. Создать проект

```bash
python ncrew_cli.py init my_project
```

### 2. Отредактировать config.yaml

```bash
nano ~/.ncrew/my_project/config.yaml
```

Добавьте роли по примеру выше.

### 3. Создать промпты

Промпты можно создать:
- Через веб-интерфейс (кнопка "Настройка ролей")
- Напрямую в `~/.ncrew/prompts/`

### 4. Запустить

```bash
python main.py
```

## CLI команды

```bash
# Создать проект
python ncrew_cli.py init <project_name>

# Список проектов
python ncrew_cli.py list

# Переключить проект
python ncrew_cli.py switch <project_name>

# Текущий проект
python ncrew_cli.py current

# Удалить проект
python ncrew_cli.py delete <project_name>
```

## UI изменения

- Новый прототип UI: `templates/projects_sidebar_ui.html`
- Боковая панель со списком проектов
- Кнопка "+ Новый проект"
- Кнопки навигации внизу (БЕЗ заголовка "Быстрые действия")
- Редактор промптов (кнопка "Настройка ролей")

## Изменения в коде

### app/config_manager.py

Новый модуль для управления проектами:
- `ProjectConfig` - конфигурация проекта
- `MultiProjectManager` - менеджер проектов
- Методы для работы с промптами

### app/config.py

Переписан для работы с `config.yaml`:
- `RoleConfig.prompt_file` вместо `system_prompt_file`
- `RoleConfig.telegram_bot_token` в конфиге роли
- Загрузка из `~/.ncrew/<project>/config.yaml`
- Промпты из `~/.ncrew/prompts/`

### ncrew_cli.py

CLI для управления проектами:
- `init` - создать проект
- `list` - список проектов
- `switch` - переключить проект
- `current` - текущий проект
- `delete` - удалить проект

## Backward compatibility

❌ **Обратная совместимость отсутствует.**

Это MVP-решение, fallback'ов и миграций нет.

Старые конфигурации нужно перенести вручную:

1. Создать проект: `python ncrew_cli.py init old_project`
2. Скопировать настройки из `.env` в `config.yaml`
3. Скопировать роли из `roles/agents.yaml` в `config.yaml`
4. Скопировать промпты в `~/.ncrew/prompts/`

## API изменения

### До

```python
Config.MAIN_BOT_TOKEN  # Из .env
Config.load_roles(Path("roles/agents.yaml"))
role.system_prompt_file  # Путь к промпту
```

### После

```python
Config.MAIN_BOT_TOKEN  # Из config.yaml проекта
Config.load_roles()  # Из текущего проекта
role.prompt_file  # Имя файла в ~/.ncrew/prompts/
```

## Тестирование

### Создание тестового проекта

```python
from app.config_manager import multi_project_manager

config = {
    "main_bot_token": "test_token",
    "target_chat_id": 12345,
    "roles": [
        {
            "role_name": "test_role",
            "display_name": "Test Role",
            "telegram_bot_name": "Test_Bot",
            "prompt_file": "test_prompt.md",
            "agent_type": "gemini_acp",
            "cli_command": "gemini --experimental-acp"
        }
    ]
}

project = multi_project_manager.create_project("test_project", config)
```

### Работа с промптами

```python
# Сохранить промпт
multi_project_manager.save_prompt("test_prompt", "# Test prompt content")

# Загрузить промпт
content = multi_project_manager.load_prompt("test_prompt")

# Список промптов
prompts = multi_project_manager.list_prompts()
```

## Известные ограничения

1. **Нет fallback на старую систему** - только новый формат
2. **Нет автоматической миграции** - перенос вручную
3. **Промпты общие** - изменение влияет на все проекты
4. **Требуется Python 3.10+** - для новых фич

## Troubleshooting

### "No project selected"

```bash
python ncrew_cli.py list
python ncrew_cli.py switch <project_name>
```

### "No roles in config.yaml"

Отредактируйте `~/.ncrew/<project>/config.yaml` и добавьте роли.

### "Prompt file not found"

Создайте промпт в `~/.ncrew/prompts/<prompt_file>.md`.

## Ссылки

- [MULTIPROJECT_ARCHITECTURE.md](./MULTIPROJECT_ARCHITECTURE.md) - полная документация
- [README_SIDEBAR_UI.md](./README_SIDEBAR_UI.md) - документация UI
- [templates/projects_sidebar_ui.html](./templates/projects_sidebar_UI.html) - прототип UI

## Заключение

✅ Система готова к использованию  
✅ Простой MVP-подход  
✅ Изоляция проектов  
✅ Общие промпты  
✅ CLI для управления  
✅ Никаких fallback'ов и сложностей
