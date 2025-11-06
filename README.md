# NeuroCrew Lab

🚀 **Telegram-based orchestration platform for autonomous AI coding agents**

NeuroCrew Lab coordinates a roster of role-specific assistants inside a Telegram group. Each role talks directly to the official **Qwen Code 0.1.4** CLI via the ACP protocol, keeping long-lived sessions and streaming responses back to the chat.

## 🎯 MVP Features

- **Telegram Bot Interface**: Simple chat-based interaction
- **Multi-Agent Orchestration**: Sequential processing through multiple AI agents
- **Context Management**: Maintains conversation history and context
- **File-based Storage**: Persistent conversation history
- **Error Handling**: Graceful error recovery and logging

## 🏗️ Architecture

### Role-Based Puppet Master Architecture

NeuroCrew Lab uses a **role-based orchestration system** where each AI agent represents a specific role (Software Developer, Code Review, Architect, etc.). The system maintains collaborative discussions between roles until consensus is reached.

```
User → Group Chat → Listener Bot → NeuroCrew Core → Role Sequence → CLI Agents → Actor Bots → Group Chat
```

### Components

- **Listener Bot**: Reads every message in the target group chat
- **NeuroCrew Core**: Coordinates role-based agents, maintains conversation context, manages stateful sessions
- **Role Configuration**: YAML-based role definitions in `roles/agents.yaml` with system prompts, CLI commands, and bot tokens
- **Connector**: `QwenACPConnector` handles ACP protocol communication with Qwen CLI agents
- **Actor Bots**: Role-specific bots that respond under their designated names
- **File Storage**: Persistent conversation history and session state
- **Target Chat Filtering**: Ensures operation only in designated Telegram groups

### Workflow

1. **User sends message** in the target group chat
2. **Listener Bot** reads the message (only works in TARGET_CHAT_ID)
3. **NeuroCrew Core** processes message and selects agent
4. **CLI Agent** generates response via connector
5. **Core returns** (agent_name, raw_response) tuple
6. **Actor Bot** sends formatted response from its own account
7. **Conversation history** is maintained in files

## 📦 Installation

### Prerequisites

- Python 3.10+ (the project uses `asyncio` extensively)
- Node.js 20+ (required by the Qwen CLI)
- Telegram bot tokens for the listener bot and every actor bot
- Qwen CLI 0.1.4 authenticated via OAuth

Install and authenticate the CLI once:

```bash
npm install -g @qwen-code/qwen-code@0.1.4
qwen --version          # should print 0.1.4
qwen                    # run once, choose OAuth in the interactive menu
```

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ncrew
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. **Run the application**
   ```bash
   python main.py
   ```

## ⚙️ Configuration

### Role Configuration

Roles are defined in `roles/agents.yaml`. Each role specifies:
- `role_name`: Unique identifier
- `display_name`: Human-readable name
- `telegram_bot_name`: Bot identifier for token lookup
- `system_prompt_file`: Path to role's system prompt
- `agent_type`: Connector type (currently "qwen_acp")
- `cli_command`: Command to launch the agent

### Environment Variables

```env
# Main bot that listens to the target chat
MAIN_BOT_TOKEN=your_listener_bot_token

# Telegram group ID where NeuroCrew operates
TARGET_CHAT_ID=123456789

# Role-specific bot tokens (automatically mapped from roles/agents.yaml)
SOFTWAREDEVBOT_TOKEN=token_for_software_dev_bot
CODEREVIEWBOT_TOKEN=token_for_code_review_bot
ARCHITECTBOT_TOKEN=token_for_architect_bot
DEVOPSBOT_TOKEN=token_for_devops_bot
SCRUMMASTERBOT_TOKEN=token_for_scrum_master_bot
# Tokens for inactive roles can be omitted

# Optional: adjust runtime behaviour
MAX_CONVERSATION_LENGTH=50
AGENT_TIMEOUT=120
LOG_LEVEL=INFO
DATA_DIR=./data
```

### Puppet Master Architecture Setup

NeuroCrew Lab uses a **"Puppet Master"** layout:

1. The listener bot (MAIN_BOT_TOKEN) monitors the group.
2. The core routes each user message through the role sequence.
3. Actor bots reply with the connector output from their respective accounts.
4. Only messages from `TARGET_CHAT_ID` are processed; everything else is ignored.

Make sure all bots are added to the same group with the appropriate permissions (listener requires `Read Messages`; actors need `Send Messages`).

## 🤖 Supported Roles & Agents

The system supports multiple roles, each powered by **Qwen Code 0.1.4** via ACP protocol:

- **Software Developer**: Code implementation and technical solutions
- **Code Review**: Quality assurance and code analysis
- **Senior Architect**: System design and architectural decisions
- **DevOps Senior**: Infrastructure and deployment
- **Scrum Master**: Process coordination and team facilitation

Additional roles can be added by extending `roles/agents.yaml`.

## 📱 Telegram Commands

- `/start` - Welcome message and introduction
- `/help` - Help information and available commands
- `/reset` - Clear conversation history
- `/status` - Check agent availability status

## 🔄 Workflow

1. **User sends message** to Telegram bot
2. **Bot processes message** through NeuroCrew core
3. **Core selects agent** based on sequence
4. **Connector executes** CLI agent with context
5. **Response is formatted** and sent back to user
6. **Conversation history** is maintained in files

## 📁 Project Structure

```
ncrew/
├── main.py                 # Application entry point
├── config.py               # Configuration management
├── telegram_bot.py         # Telegram bot interface
├── ncrew.py                # Core business logic
├── connectors/             # AI agent connectors
│   ├── base.py             # Shared async process wrapper
│   └── qwen_acp_connector.py  # Qwen ACP 0.1.4 connector
├── storage/               # Data persistence
│   └── file_storage.py    # File-based storage
├── utils/                 # Utilities
│   ├── logger.py          # Logging utilities
│   └── formatters.py      # Message formatting
├── data/                  # Runtime data
│   ├── conversations/     # Chat histories
│   └── logs/             # Application logs
└── tests/               # Pytest suite (mocked ACP server)
```

## 🐛 Development

### Running Tests

```bash
pytest
```

Enable DEBUG logging during local runs if you need detailed ACP traces:

```bash
LOG_LEVEL=DEBUG python main.py
```

## 📈 MVP Status

✅ **Completed:**
- Project architecture specification
- Puppet Master architecture implementation
- Multi-bot configuration system (MAIN_BOT_TOKEN, TARGET_CHAT_ID, role-based `_TOKEN` env vars)
- Core system refactoring (returns raw responses instead of formatted)
- Telegram bot Puppet Master logic (actor bot coordination)
- File storage system implementation
- Target chat filtering and security
- Group chat integration

🚧 **In Progress:**
- Full end-to-end Telegram verification with the new ACP connector
- Documentation of operating procedures and troubleshooting

📋 **Planned:**
- Bring remaining providers onto the ACP stack
- Performance tuning and observability
- Advanced features beyond MVP
- Enhanced monitoring and logging

## 🤝 Contributing

This is currently an MVP project. Contributions welcome for:

- Additional agent connectors
- Enhanced error handling
- Performance optimizations
- Security improvements
- Documentation improvements

## 📄 License

[Add your license information here]

---

**NeuroCrew Lab** - Where multiple AI agents work together for you! 🚀




### **Настройка Окружения Telegram: Предварительные Требования**

Для корректной работы приложения **NeuroCrew Lab** необходимо предварительно настроить окружение в Telegram в соответствии с архитектурой "Оркестратор-Кукловод". Это разовая процедура, которая обеспечивает централизованное управление и позволяет разным агентам общаться в одном чате от своего имени.

#### Шаг 1: Создание N+1 Ботов

Вам потребуется создать по одному боту для каждого AI-агента и еще один, главный, бот для управления всем процессом. Все боты создаются через официальный **`@BotFather`** в Telegram.

1.  **1 Главный Бот-Слушатель (`Listener Bot`)**
    *   **Назначение:** Этот бот будет единственным, кто *читает* все сообщения в групповом чате. Вся логика приложения будет работать через него.
    *   **Действие:** Создайте бота (например, `@NeuroCrewLabListenerBot`) и **сохраните его API-токен**. Этот токен будет использоваться как главный токен приложения (`MAIN_BOT_TOKEN`).

2.  **N Ботов-Актеров (`Actor Bots`)**
    *   **Назначение:** Эти боты служат "цифровыми аватарами" для ваших CLI-агентов. Они используются только для *отправки* сообщений от имени соответствующего агента.
    *   **Действие:** Создайте по одному боту для каждой роли из `roles/agents.yaml` (например, `@SoftwareDevBot`, `@CodeReviewBot`, `@ScrumMasterBot`). **Сохраните API-токен каждого из них.**

**Результат этого шага:** У вас должен быть список из N+1 API-токенов.

#### Шаг 2: Настройка Группового Чата

1.  **Создание Группы:**
    *   Создайте новую группу в Telegram. Это будет рабочее пространство для ваших AI-агентов.

2.  **Добавление Участников:**
    *   Добавьте в созданную группу **всех** ботов, созданных на Шаге 1 (и "Слушателя", и всех "Актеров").
    *   Добавьте себя (и других пользователей, которые будут участвовать в диалоге).

3.  ⚠️ **Критически важный шаг: Отключение режима приватности для Бота-Слушателя.**
    *   По умолчанию боты в группах не видят сообщения, которые не адресованы им напрямую. Чтобы ваш главный бот-слушатель мог читать всю переписку, этот режим нужно отключить.
    *   **Как это сделать:**
        1.  Откройте диалог с **`@BotFather`**.
        2.  Отправьте команду `/mybots`.
        3.  Выберите вашего **Главного Бота-Слушателя** из списка.
        4.  Нажмите на кнопку "Bot Settings".
        5.  Нажмите "Group Privacy".
        6.  Убедитесь, что режим выключен. Если там написано "Turn on", значит все хорошо. Если написано "Turn off" — нажмите на нее. Статус должен быть: `Privacy mode is disabled...`.

#### Итог: Что у вас должно быть готово

Перед тем как конфигурировать и запускать приложение `NeuroCrew Lab`, убедитесь, что у вас есть:

1.  **Список всех N+1 API-токенов**, разделенных по ролям (1 главный, N для агентов).
2.  **ID группового чата (Chat ID)**, в котором находятся все участники.
    *   *Как узнать Chat ID:* Добавьте в вашу группу бота `@userinfobot`, он пришлет информацию о чате, включая его ID (обычно это отрицательное число). После получения ID бота можно удалить.

Эти значения будут использоваться для конфигурации приложения через переменные окружения или конфигурационный файл.
