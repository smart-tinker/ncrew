### **Техническая Спецификация: Переход на Ролевую Архитектуру**

**1. Видение и Цель**

Цель этого рефакторинга — превратить **NeuroCrew Lab** из системы с простой ротацией *типов агентов* в гибкую платформу, управляемую **"Ролями"**. Каждая "Роль" представляет собой уникальную, настраиваемую "личность" со своим поведением (системный промпт), инструментарием (тип agentic CLI и его настройки) и аватаром (отдельный бот в Telegram).

Вся конфигурация ролей должна быть вынесена в единый, легко редактируемый файл.

**2. Ключевые Архитектурные Изменения**

1.  **Централизованная Конфигурация Ролей:** Вместо жестко закодированной последовательности агентов, система будет управляться файлом `agents.yaml`. Этот файл становится "Реестром Ролей" и единственным источником правды о составе и поведении команды агентов.
2.  **Ролевая Очередь:** Оркестратор будет вызывать не *типы агентов* (`qwen`, `gemini`), а *роли* (`python_junior`, `code_reviewer`) в последовательности, заданной в `agents.yaml`.
3.  **Контекст с Системным Промптом:** Перед вызовом CLI, к истории диалога ("дельте") будет добавляться системный промпт, определяющий поведение и задачу текущей роли.
4.  **Универсальные Коннекторы:** Коннекторы перестают быть привязанными к конкретным моделям или путям. Они становятся универсальными исполнителями для своего *типа* CLI, принимая точную команду и промпт для выполнения.

**3. Спецификация по Компонентам**

#### **Задача 1: Создание "Реестра Ролей" и папки с промптами**

**1.1. Создать файл `agents.yaml` в корне проекта.**
Этот файл будет содержать список всех доступных ролей.

```yaml
# agents.yaml

# Список всех доступных ролей. Порядок определяет очередь вызова.
roles:
  - role_name: python_junior_dev
    telegram_bot_name: PythonJuniorBot
    system_prompt_file: prompts/python_junior.txt
    agent_type: qwen
    command: "qwen-code --model qwen-turbo --temperature 0.7"

  - role_name: senior_code_reviewer
    telegram_bot_name: CodeReviewerBot
    system_prompt_file: prompts/code_reviewer.txt
    agent_type: gemini
    command: "gemini-cli --model gemini-1.5-pro --strict"

  - role_name: qa_engineer
    telegram_bot_name: QABot
    system_prompt_file: prompts/qa_engineer.txt
    agent_type: claude
    command: "claude-code --model claude-3-opus"
```

**1.2. Создать папку `prompts/` в корне проекта.**
В этой папке будут храниться текстовые файлы с системными промптами.

*   Создать файл `prompts/python_junior.txt`:
    ```txt
    Ты — начинающий Python-разработчик. Твой стиль — писать простой, понятный код с большим количеством комментариев. Ты можешь допускать небольшие ошибки, но всегда стараешься следовать заданию.
    ```*   Создать аналогичные файлы для `code_reviewer.txt` и `qa_engineer.txt`.

#### **Задача 2: Обновление Конфигурации (`.env.example`, `config.py`, `requirements.txt`)**

**2.1. Модифицировать `requirements.txt`:**
Добавить библиотеку для парсинга YAML.

```diff
# requirements.txt
python-telegram-bot==20.8
python-dotenv==1.0.0
aiofiles==23.2.1
pydantic==2.5.0
+ PyYAML==6.0.1
```

**2.2. Модифицировать `.env.example`:**
Заменить `AGENT_TOKENS` на `TELEGRAM_BOT_TOKENS` для большей ясности.

```diff
- AGENT_TOKENS=qwen:token1,gemini:token2,...
+ # Имена ботов (PythonJuniorBot, etc.) должны совпадать с telegram_bot_name в agents.yaml
+ TELEGRAM_BOT_TOKENS=PythonJuniorBot:token1,CodeReviewerBot:token2,QABot:token3
```

**2.3. Рефакторинг `config.py`:**

```python
# config.py
import os
from typing import Dict, List, Any
from pathlib import Path
from dotenv import load_dotenv
import yaml # <-- Импортировать

load_dotenv()

# Добавить dataclass для удобного хранения конфигурации роли
from dataclasses import dataclass

@dataclass
class RoleConfig:
    role_name: str
    telegram_bot_name: str
    system_prompt_file: Path
    agent_type: str
    command: str
    system_prompt: str = "" # Будет загружен при инициализации


class Config:
    # ... (существующие переменные MAIN_BOT_TOKEN, TARGET_CHAT_ID) ...
    
    # Заменить AGENT_TOKENS
    TELEGRAM_BOT_TOKENS: Dict[str, str] = {}

    # УДАЛИТЬ: AGENT_SEQUENCE, так как он будет загружаться из YAML
    # УДАЛИТЬ: CLI_PATHS, так как команды теперь в YAML

    # Новые переменные для хранения ролей
    ROLES: List[RoleConfig] = []
    ROLES_BY_NAME: Dict[str, RoleConfig] = {}

    @classmethod
    def load_roles(cls, config_path: Path = Path('agents.yaml')):
        """Загружает и парсит конфигурацию ролей из agents.yaml."""
        if not config_path.exists():
            raise FileNotFoundError("Файл agents.yaml не найден.")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        cls.ROLES = []
        for role_data in config_data.get('roles', []):
            role_cfg = RoleConfig(**role_data)
            # Загружаем содержимое системного промпта
            try:
                with open(role_cfg.system_prompt_file, 'r', encoding='utf-8') as pf:
                    role_cfg.system_prompt = pf.read().strip()
            except FileNotFoundError:
                raise FileNotFoundError(f"Файл промпта не найден: {role_cfg.system_prompt_file}")
            
            cls.ROLES.append(role_cfg)
        
        cls.ROLES_BY_NAME = {role.role_name: role for role in cls.ROLES}

    @classmethod
    def _load_telegram_bot_tokens(cls):
        # Переименовать из _load_agent_tokens
        # ... (логика парсинга TELEGRAM_BOT_TOKENS остается прежней) ...

# В конце файла вызвать загрузчики
Config._load_telegram_bot_tokens()
Config.load_roles()
```

#### **Задача 3: Рефакторинг Ядра (`ncrew.py`)**

**3.1. Изменить `__init__`:**
Ядро теперь работает с ролями из `Config`.

```python
# ncrew.py
class NeuroCrewLab:
    def __init__(self, storage: Optional[FileStorage] = None):
        # ...
        self.connectors: Dict[str, BaseConnector] = {}
        
        # Загружаем роли и последовательность из Config
        self.roles_config = Config.ROLES_BY_NAME
        self.role_sequence = [role.role_name for role in Config.ROLES]
        
        self.chat_role_pointers: Dict[int, int] = {} # Переименовать chat_agent_pointers

        self.logger.info(f"Роли загружены. Последовательность: {self.role_sequence}")
```

**3.2. Изменить `_get_next_role` (ранее `_get_next_agent`):**
Логика остается round-robin, но итерируется по `self.role_sequence`.

**3.3. Изменить `handle_message`:**
Метод должен возвращать `(RoleConfig, str)` — объект конфигурации роли и "сырой" ответ.

**3.4. Изменить `_process_with_agent` на `_process_with_role`:**
Этот метод теперь принимает `RoleConfig`.

```python
# ncrew.py -> class NeuroCrewLab
async def _process_with_role(self, chat_id: int, role_config: RoleConfig) -> str:
    agent_type = role_config.agent_type
    if agent_type not in self.connectors:
        return f"❌ Error: Коннектор для типа '{agent_type}' не найден."

    connector = self.connectors[agent_type]
    
    # 1. Собрать полный промпт
    system_prompt = role_config.system_prompt
    conversation_history = await self.storage.load_conversation(chat_id)
    # Форматируем историю в виде текста
    history_text = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history])
    full_prompt = f"{system_prompt}\n\n--- ДИАЛОГ ---\n\n{history_text}"

    # 2. Вызвать коннектор с командой и промптом
    response = await connector.execute(role_config.command, full_prompt)
    
    # ... (сохранение ответа в историю) ...
    
    return response # Вернуть "сырой" ответ
```

#### **Задача 4: Рефакторинг Коннекторов (`connectors/`)**

**4.1. Обновить `connectors/base.py`:**
Изменить сигнатуру метода `execute`.

```python
# connectors/base.py
class BaseConnector(ABC):
    # ...

    @abstractmethod
    async def execute(self, command: str, full_prompt: str) -> str:
        """
        Выполняет CLI-агент с указанной командой и промптом.
        """
        pass
```

**4.2. Обновить реализации коннекторов (например, `qwen_connector.py`):**
Адаптировать метод `execute` под новый интерфейс.

```python
# connectors/qwen_connector.py
class QwenConnector(BaseConnector):
    # ...

    async def execute(self, command: str, full_prompt: str) -> str:
        # self.agent_path больше не используется
        command_parts = command.split()
        
        process = await asyncio.create_subprocess_exec(
            *command_parts, # Используем команду из YAML
            stdin=asyncio.subprocess.PIPE,
            # ...
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(input=full_prompt), # Передаем полный промпт
            timeout=self.timeout
        )
        
        # ... (остальная логика обработки ответа) ...```

#### **Задача 5: Рефакторинг Telegram Бота (`telegram_bot.py`)**

**5.1. Обновить `handle_message`:**
Теперь метод получает `(RoleConfig, str)` от `ncrew` и использует `telegram_bot_name` для отправки.

```python
# telegram_bot.py -> class TelegramBot
async def handle_message(self, update: Update, context: CallbackContext):
    # ...
    role_config, raw_response = await self.ncrew.handle_message(chat_id, user_text)

    if role_config and raw_response:
        # Успешный ответ от роли
        bot_name = role_config.telegram_bot_name
        actor_token = Config.TELEGRAM_BOT_TOKENS.get(bot_name)
        
        if actor_token:
            # Отправляем от имени актера
            from telegram import Bot
            actor_bot = Bot(token=actor_token)
            # ... (логика форматирования и отправки) ...
        else:
            # Обработка ошибки, если токен не найден
            await update.message.reply_text(f"Ошибка: Токен для бота '{bot_name}' не найден.")
    # ...
```

**4. Критерии Готовности MVP**

1.  Приложение успешно запускается, читает `agents.yaml` и инициализирует все роли.
2.  В групповом чате сообщения пользователя обрабатываются ролями в той последовательности, которая задана в `agents.yaml`.
3.  Каждый ответ публикуется от имени того Telegram-бота, который указан в поле `telegram_bot_name` для текущей роли.
4.  При вызове CLI-агента используется точная `command`, указанная в `agents.yaml`.
5.  Перед историей диалога в промпт агента подставляется текст из файла, указанного в `system_prompt_file`.
6.  `README.md` и `.env.example` обновлены с учетом новой структуры конфигурации.