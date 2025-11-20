# 🔌 Коннекторы NeuroCrew Lab

## Что такое коннектор

Коннектор - это программный адаптер, который обеспечивает взаимодействие NeuroCrew Lab с конкретным AI-агентом через его официальный CLI. Каждый коннектор инкапсулирует специфику протокола взаимодействия, управляет жизненным циклом CLI-процесса и предоставляет единый интерфейс для оркестратора.

### Типы коннекторов

1. **ACP-коннекторы** (Agent Communication Protocol) - для агентов с поддержкой долгоживущих интерактивных сессий
2. **Headless CLI-коннекторы** - для агентов, работающих в неинтерактивном режиме

## Базовая архитектура

### BaseConnector

```python
class BaseConnector(ABC):
    """Базовый класс для всех коннекторов."""
    
    @abstractmethod
    async def launch(self) -> bool:
        """Запуск коннектора и инициализация сессии."""
        pass
    
    @abstractmethod
    async def execute(self, prompt: str) -> str:
        """Выполнение запроса к AI-агенту."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Корректное завершение работы коннектора."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Проверка доступности коннектора."""
        pass
```

### BaseACPConnector

Расширяет `BaseConnector` для работы с ACP-протоколом:

- **Handshake** - установление соединения с агентом
- **Keep-alive** - поддержание активной сессии
- **Recovery** - восстановление после обрыва связи
- **Stream processing** - потоковая обработка ответов

### BaseCLIConnector

Расширяет `BaseConnector` для headless CLI:

- **Process spawning** - запуск CLI-процесса для каждого запроса
- **JSON streaming** - обработка потокового JSON-вывода
- **Timeout handling** - управление таймаутами выполнения
- **Error parsing** - парсинг ошибок CLI

## Доступные коннекторы

### OpenCode ACP Connector

**Файл:** `app/connectors/opencode_acp_connector.py`

**Поддерживаемый агент:** OpenCode CLI

**Протокол:** ACP (Agent Communication Protocol)

**CLI команда:** `opencode acp`

**Конфигурация в roles/agents.yaml:**
```yaml
- role_name: code_review
  agent_type: opencode_acp
  cli_command: "opencode acp"
  telegram_bot_name: Code_Review_Bot
```

**Особенности:**
- Поддерживает долгоживущие сессии
- Автоматическое восстановление соединения
- Потоковая передача ответов
- Встроенная обработка ошибок ACP

**Требования:**
- Установленный `opencode` CLI
- Аутентификация через `opencode auth login`

**Environment variables:**
- `OPENCODE_BOT_TOKEN` - токен для Telegram-бота роли

### Qwen ACP Connector

**Файл:** `app/connectors/qwen_acp_connector.py`

**Поддерживаемый агент:** Qwen Code CLI

**Протокол:** ACP

**CLI команда:** `qwen --experimental-acp`

**Конфигурация:**
```yaml
- role_name: product_owner
  agent_type: qwen_acp
  cli_command: "qwen --experimental-acp"
  telegram_bot_name: Product_Owner_Bot
```

**Особенности:**
- Экспериментальная поддержка ACP
- Управление контекстом через Qwen CLI
- Retry-логика при нестабильном соединении
- Оптимизация для длинных промптов

**Требования:**
- `npm install -g @qwen-code/qwen-code@0.1.4`
- OAuth-аутентификация через `qwen`

### Gemini ACP Connector

**Файл:** `app/connectors/gemini_acp_connector.py`

**Поддерживаемый агент:** Gemini CLI

**Протокол:** ACP

**CLI команда:** `gemini --experimental-acp`

**Конфигурация:**
```yaml
- role_name: software_developer
  agent_type: gemini_acp
  cli_command: "gemini --experimental-acp"
  telegram_bot_name: Software_Dev_Bot
```

**Особенности:**
- Поддержка approval mode
- Расширенная обработка таймаутов
- Специальная обработка multi-turn диалогов
- Интеграция с Google Cloud аутентификацией

**Требования:**
- `go install github.com/google/gemini-cli@latest`
- Настройка `~/.gemini/settings.json`

**Environment variables:**
- `GEMINI_MAX_TIMEOUTS` - максимальное количество таймаутов (по умолчанию: 3)

### Codex CLI Connector

**Файл:** `app/connectors/codex_cli_connector.py`

**Поддерживаемый агент:** OpenAI Codex

**Протокол:** Headless CLI

**CLI команда:** `codex exec --json --full-auto --sandbox workspace-write --skip-git-repo-check`

**Конфигурация:**
```yaml
- role_name: devops_senior
  agent_type: codex_cli
  cli_command: "codex exec --json --full-auto --sandbox workspace-write --skip-git-repo-check"
  telegram_bot_name: DevOps_Senior_Bot
```

**Особенности:**
- Неинтерактивный режим выполнения
- JSON-формат вывода
- Sandbox-безопасность
- Автоматическое управление git-репозиторием

**Требования:**
- `npm install -g @openai/codex`
- Платная подписка OpenAI (Plus/Pro/Team/Enterprise)
- Локальная аутентификация через `codex login`

### Claude CLI Connector

**Файл:** `app/connectors/claude_cli_connector.py`

**Поддерживаемый агент:** Claude Code

**Протокол:** Headless CLI

**CLI команда:** `claude -p --output-format stream-json --permission-mode bypassPermissions --dangerously-skip-permissions --verbose`

**Конфигурация:**
```yaml
- role_name: scrum_master
  agent_type: claude_cli
  cli_command: "claude -p --output-format stream-json --permission-mode bypassPermissions --dangerously-skip-permissions --verbose"
  telegram_bot_name: Scrum_Master_Bot
```

**Особенности:**
- Потоковая обработка JSON
- Обход разрешений для автоматизации
- Устойчивость к длинным сессиям
- Детальное логирование

**Требования:**
- `curl -fsSL https://claude.ai/install.sh | bash`
- Настройка токена через `claude setup-token`
- Платная подписка Anthropic

## Добавление нового коннектора

### Шаблон нового коннектора

```python
from app.connectors.base import BaseConnector
from typing import Optional
import asyncio
import subprocess

class NewAgentConnector(BaseConnector):
    """Коннектор для нового AI-агента."""
    
    def __init__(self, cli_command: str, timeout: float = 300.0):
        self.cli_command = cli_command
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.is_launched = False
    
    async def launch(self) -> bool:
        """Запуск коннектора."""
        try:
            # Запуск CLI-процесса
            self.process = subprocess.Popen(
                self.cli_command.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            self.is_launched = True
            return True
        except Exception as e:
            return False
    
    async def execute(self, prompt: str) -> str:
        """Выполнение запроса."""
        if not self.is_launched:
            await self.launch()
        
        try:
            # Отправка запроса
            self.process.stdin.write(prompt + "\n")
            self.process.stdin.flush()
            
            # Чтение ответа
            response = await asyncio.wait_for(
                self._read_output(), 
                timeout=self.timeout
            )
            return response
        except asyncio.TimeoutError:
            raise TimeoutError(f"Agent response timeout after {self.timeout}s")
    
    async def shutdown(self) -> None:
        """Завершение работы."""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
        self.is_launched = False
    
    async def health_check(self) -> bool:
        """Проверка доступности."""
        return self.is_launched and self.process and self.process.poll() is None
    
    async def _read_output(self) -> str:
        """Чтение вывода процесса."""
        # Реализация чтения stdout
        pass
```

### Регистрация коннектора

1. **Добавить в `app/connectors/__init__.py`:**
```python
from .new_agent_connector import NewAgentConnector

CONNECTOR_REGISTRY = {
    # ... существующие коннекторы ...
    'new_agent': NewAgentConnector,
}
```

2. **Добавить спецификацию:**
```python
def get_connector_spec(agent_type: str) -> Optional[Dict[str, Any]]:
    specs = {
        # ... существующие спецификации ...
        'new_agent': {
            'requires_cli': True,
            'supports_acp': False,
            'default_timeout': 300.0,
            'description': 'New AI Agent Connector'
        }
    }
    return specs.get(agent_type)
```

3. **Обновить roles/agents.yaml:**
```yaml
- role_name: new_role
  agent_type: new_agent
  cli_command: "new-agent-cli --mode interactive"
  telegram_bot_name: New_Agent_Bot
```

## Известные ограничения

### Общие ограничения

- **Процессорные ресурсы:** каждый коннектор запускает отдельный subprocess
- **Память:** долгоживущие ACP-сессии потребляют память
- **Сетевые зависимости:** все коннекторы требуют интернет-соединения
- **Локальная аутентификация:** требуется предварительная настройка CLI

### Специфические ограничения

#### OpenCode ACP
- Ограничение на количество одновременных ACP-сессий
- Требует стабильного интернет-соединения

#### Qwen ACP
- Экспериментальный протокол, возможны изменения
- Ограничения на длину промпта

#### Gemini ACP
- Зависит от Google Cloud аутентификации
- Квоты API Google

#### Codex CLI
- Требует платной подписки OpenAI
- Ограничения на количество запросов в минуту

#### Claude CLI
- Требует платной подписки Anthropic
- Ограничения на длину контекста

## Retry-логика и обработка ошибок

### Стратегия повторных попыток

```python
async def execute_with_retry(self, prompt: str, max_retries: int = 2) -> str:
    """Выполнение с retry-логикой."""
    for attempt in range(max_retries + 1):
        try:
            return await self.execute(prompt)
        except TimeoutError:
            if attempt == max_retries:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            if attempt == max_retries:
                raise
            await self.launch()  # Пересоздание сессии
```

### Типы обрабатываемых ошибок

- **TimeoutError** - превышение времени ожидания ответа
- **ConnectionError** - потеря соединения с CLI
- **ProcessError** - падение CLI-процесса
- **AuthenticationError** - проблемы с аутентификацией
- **RateLimitError** - превышение квот API

## Мониторинг и отладка

### Логирование

Каждый коннектор логирует:
- Запуск и завершение сессии
- Отправленные промпты (без чувствительных данных)
- Время выполнения запросов
- Ошибки и retry-попытки

### Метрики

- `connector_launch_count` - количество запусков коннектора
- `connector_execution_time` - время выполнения запросов
- `connector_error_count` - количество ошибок
- `connector_retry_count` - количество retry-попыток

### Health checks

Периодическая проверка доступности коннекторов:
```python
async def periodic_health_check():
    """Периодическая проверка состояния коннекторов."""
    for connector in active_connectors:
        if not await connector.health_check():
            logger.warning(f"Connector {connector} is unhealthy")
            await connector.launch()  # Попытка перезапуска
```

## Безопасность

### Изоляция процессов

- Каждый коннектор работает в отдельном subprocess
- Ограниченные права доступа к файловой системе
- Автоматическая очистка ресурсов при ошибках

### Управление секретами

- Токены хранятся только в environment variables
- CLI-аутентификация происходит вне NeuroCrew
- Логирование с маскировкой чувствительных данных

### Валидация входных данных

- Проверка промптов на инъекции
- Ограничение длины сообщений
- Санитизация специальных символов