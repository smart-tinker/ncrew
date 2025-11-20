# 🧪 Тестирование NeuroCrew Lab

## Обзор

Тестовая инфраструктура NeuroCrew Lab построена на **pytest** с поддержкой **asyncio** для асинхронных тестов. Покрывает все основные компоненты: коннекторы, ядро оркестрации, Telegram-интеграцию и веб-сервер.

## Структура тестов

```
tests/
├── __init__.py
├── conftest.py                 # Общие фикстуры
├── unit/                       # Unit-тесты
│   ├── test_ncrew_core.py      # Тесты ядра системы
│   ├── test_config.py          # Тесты конфигурации
│   └── test_file_storage.py    # Тесты файлового хранилища
├── connectors/                  # Тесты коннекторов
│   ├── test_base_connector.py  # Базовые тесты коннекторов
│   ├── test_opencode_acp.py    # OpenCode ACP
│   ├── test_qwen_acp.py        # Qwen ACP
│   ├── test_gemini_acp.py      # Gemini ACP
│   ├── test_codex_cli_connector.py  # Codex CLI
│   └── test_claude_cli_connector.py  # Claude CLI
├── interfaces/                 # Тесты интерфейсов
│   ├── test_telegram_bot.py    # Telegram-бот
│   └── test_web_server.py      # Веб-сервер
├── integration/                # Интеграционные тесты
│   ├── test_start_integration.py  # Запуск системы
│   ├── test_full_flow.py       # Полный цикл обработки
│   └── test_role_sequence.py   # Последовательность ролей
└── e2e/                       # End-to-end тесты
    ├── test_telegram_flow.py   # Полный поток в Telegram
    └── test_web_interface.py   # Веб-интерфейс
```

## Настройка тестового окружения

### Установка зависимостей

```bash
# Установка тестовых зависимостей
pip install pytest pytest-asyncio pytest-mock pytest-cov

# Для интеграционных тестов
pip install httpx aioresponses

# Для e2e тестов
pip install selenium telegram-web-app
```

### Конфигурация pytest

#### pytest.ini

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --strict-config
    --cov=app
    --cov-report=term-missing
    --cov-report=html:htmlcov
    --cov-fail-under=80
asyncio_mode = auto
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow running tests
    external: Tests requiring external services
```

#### conftest.py

```python
import pytest
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from app.config import Config
from app.storage.file_storage import FileStorage
from app.core.engine import NeuroCrewLab

@pytest.fixture(scope="session")
def event_loop():
    """Создание event loop для асинхронных тестов."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def temp_storage():
    """Временное хранилище для тестов."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileStorage(data_dir=Path(temp_dir))
        yield storage

@pytest.fixture
async def mock_ncrew(temp_storage):
    """Мок NeuroCrewLab для тестов."""
    ncrew = NeuroCrewLab(storage=temp_storage)
    # Мокирование коннекторов
    ncrew.connector_sessions = {}
    yield ncrew

@pytest.fixture
def mock_telegram_bot():
    """Мок Telegram бота."""
    bot = Mock()
    bot.send_message = AsyncMock()
    bot.get_chat = AsyncMock()
    return bot

@pytest.fixture
def sample_role_config():
    """Пример конфигурации роли."""
    return {
        "role_name": "test_role",
        "display_name": "Test Role",
        "telegram_bot_name": "Test_Role_Bot",
        "system_prompt_file": "test_prompt.md",
        "agent_type": "test_connector",
        "cli_command": "test-cli --arg",
        "description": "Test role for testing"
    }
```

## Запуск тестов

### Все тесты

```bash
# Запуск всех тестов
pytest

# С покрытием кода
pytest --cov=app --cov-report=html

# Подробный вывод
pytest -v
```

### Категории тестов

```bash
# Только unit-тесты
pytest -m unit

# Только интеграционные тесты
pytest -m integration

# Исключить медленные тесты
pytest -m "not slow"

# Только тесты, требующие внешние сервисы
pytest -m external
```

### Отдельные модули

```bash
# Тесты ядра
pytest tests/unit/test_ncrew_core.py

# Тесты коннекторов
pytest tests/connectors/

# Тесты веб-сервера
pytest tests/interfaces/test_web_server.py
```

### Отладка тестов

```bash
# Остановка на первом падении
pytest -x

# Вывод print statements
pytest -s

# Запуск с pdb
pytest --pdb

# Только упавшие тесты
pytest --lf
```

## Unit-тесты

### Тесты ядра системы

```python
# tests/unit/test_ncrew_core.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.core.engine import NeuroCrewLab

@pytest.mark.asyncio
async def test_ncrew_initialization(temp_storage):
    """Тест инициализации NeuroCrewLab."""
    ncrew = NeuroCrewLab(storage=temp_storage)
    
    assert ncrew.storage == temp_storage
    assert ncrew.is_role_based is True
    assert len(ncrew.roles) > 0
    assert ncrew.connector_sessions == {}

@pytest.mark.asyncio
async def test_handle_message_with_mock_connector(mock_ncrew):
    """Тест обработки сообщения с мокированным коннектором."""
    chat_id = 123456
    message = "Test message"
    
    # Мокирование коннектора
    mock_connector = AsyncMock()
    mock_connector.execute.return_value = "Test response"
    mock_ncrew.connector_sessions[(chat_id, "software_developer")] = mock_connector
    
    # Мокирование ролей
    mock_ncrew.roles = [
        Mock(role_name="software_developer", agent_type="test")
    ]
    
    # Тест обработки
    responses = []
    async for response in mock_ncrew.handle_message(chat_id, message):
        responses.append(response)
    
    assert len(responses) > 0
    mock_connector.execute.assert_called_once()

@pytest.mark.asyncio
async def test_role_sequence_validation():
    """Тест валидации последовательности ролей."""
    with patch('app.config.Config.get_role_sequence') as mock_get_roles:
        mock_get_roles.return_value = [
            Mock(role_name="role1"),
            Mock(role_name="role2")
        ]
        
        ncrew = NeuroCrewLab()
        
        # Проверка, что роли загружены и валидированы
        assert len(ncrew.roles) == 2
        assert ncrew.roles[0].role_name == "role1"
```

### Тесты файлового хранилища

```python
# tests/unit/test_file_storage.py
import pytest
from datetime import datetime
from app.storage.file_storage import FileStorage

@pytest.mark.asyncio
async def test_add_message(temp_storage):
    """Тест добавления сообщения."""
    chat_id = 123456
    
    await temp_storage.add_message(
        chat_id=chat_id,
        role_name="user",
        content="Test message",
        message_type="user_message"
    )
    
    conversation = await temp_storage.load_conversation(chat_id)
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["content"] == "Test message"
    assert conversation["messages"][0]["role_name"] == "user"

@pytest.mark.asyncio
async def test_conversation_limit(temp_storage):
    """Тест ограничения длины диалога."""
    chat_id = 123456
    
    # Добавление сообщений сверх лимита
    for i in range(150):
        await temp_storage.add_message(
            chat_id=chat_id,
            role_name="user",
            content=f"Message {i}",
            message_type="user_message"
        )
    
    conversation = await temp_storage.load_conversation(chat_id)
    assert len(conversation["messages"]) <= 100  # Стандартный лимит

@pytest.mark.asyncio
async def test_backup_and_restore(temp_storage):
    """Тест бэкапа и восстановления."""
    chat_id = 123456
    
    # Добавление сообщения
    await temp_storage.add_message(
        chat_id=chat_id,
        role_name="user",
        content="Original message",
        message_type="user_message"
    )
    
    # Изменение сообщения
    await temp_storage.add_message(
        chat_id=chat_id,
        role_name="user",
        content="Modified message",
        message_type="user_message"
    )
    
    # Восстановление из бэкапа
    restored = await temp_storage.restore_from_backup(chat_id)
    assert restored
    
    # Проверка
    conversation = await temp_storage.load_conversation(chat_id)
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["content"] == "Original message"
```

## Тесты коннекторов

### Базовые тесты коннектора

```python
# tests/connectors/test_base_connector.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.connectors.base import BaseConnector

class TestConnector(BaseConnector):
    """Тестовый коннектор."""
    
    async def launch(self) -> bool:
        return True
    
    async def execute(self, prompt: str) -> str:
        return f"Response to: {prompt}"
    
    async def shutdown(self) -> None:
        pass
    
    async def health_check(self) -> bool:
        return True

@pytest.mark.asyncio
async def test_connector_lifecycle():
    """Тест жизненного цикла коннектора."""
    connector = TestConnector()
    
    # Запуск
    launched = await connector.launch()
    assert launched is True
    
    # Выполнение
    response = await connector.execute("test prompt")
    assert "test prompt" in response
    
    # Проверка здоровья
    healthy = await connector.health_check()
    assert healthy is True
    
    # Завершение
    await connector.shutdown()

@pytest.mark.asyncio
async def test_connector_error_handling():
    """Тест обработки ошибок коннектора."""
    connector = TestConnector()
    
    # Мокирование ошибки при выполнении
    with patch.object(connector, 'execute', side_effect=Exception("Test error")):
        with pytest.raises(Exception, match="Test error"):
            await connector.execute("test")
```

### Тесты ACP коннекторов

```python
# tests/connectors/test_opencode_acp.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.connectors.opencode_acp_connector import OpenCodeACPConnector

@pytest.mark.asyncio
async def test_opencode_acp_launch():
    """Тест запуска OpenCode ACP коннектора."""
    connector = OpenCodeACPConnector("opencode acp")
    
    with patch('asyncio.create_subprocess_exec') as mock_subprocess:
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdin = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_subprocess.return_value = mock_process
        
        launched = await connector.launch()
        assert launched is True
        mock_subprocess.assert_called_once()

@pytest.mark.asyncio
async def test_opencode_acp_execute():
    """Тест выполнения запроса OpenCode ACP."""
    connector = OpenCodeACPConnector("opencode acp")
    
    # Мокирование процесса
    mock_process = Mock()
    mock_process.stdin = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.stderr = AsyncMock()
    connector.process = mock_process
    connector.is_launched = True
    
    # Мокирование ответа
    mock_process.stdout.readline.return_value = b'{"response": "Test response"}\n'
    
    response = await connector.execute("test prompt")
    assert "Test response" in response

@pytest.mark.asyncio
async def test_opencode_acp_timeout():
    """Тест таймаута OpenCode ACP."""
    connector = OpenCodeACPConnector("opencode acp", timeout=0.1)
    
    # Мокирование процесса с задержкой
    mock_process = Mock()
    mock_process.stdin = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.stderr = AsyncMock()
    connector.process = mock_process
    connector.is_launched = True
    
    # Мокирование задержки ответа
    import asyncio
    async def delayed_readline():
        await asyncio.sleep(0.2)  # Задержка больше таймаута
        return b'{"response": "Delayed response"}\n'
    
    mock_process.stdout.readline = delayed_readline
    
    with pytest.raises(TimeoutError):
        await connector.execute("test prompt")
```

### Тесты CLI коннекторов

```python
# tests/connectors/test_codex_cli_connector.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.connectors.codex_cli_connector import CodexCLIConnector

@pytest.mark.asyncio
async def test_codex_cli_execution():
    """Тест выполнения Codex CLI."""
    connector = CodexCLIConnector("codex exec --json")
    
    with patch('asyncio.create_subprocess_exec') as mock_subprocess:
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(
            b'{"response": "Generated code"}', 
            b''
        ))
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        
        response = await connector.execute("Generate Python function")
        assert "Generated code" in response
        mock_subprocess.assert_called_once()

@pytest.mark.asyncio
async def test_codex_cli_error_handling():
    """Тест обработки ошибок Codex CLI."""
    connector = CodexCLIConnector("codex exec --json")
    
    with patch('asyncio.create_subprocess_exec') as mock_subprocess:
        mock_process = Mock()
        mock_process.communicate = AsyncMock(return_value=(
            b'', 
            b'Error: Invalid request'
        ))
        mock_process.returncode = 1
        mock_subprocess.return_value = mock_process
        
        with pytest.raises(Exception, match="Error: Invalid request"):
            await connector.execute("Invalid request")
```

## Интеграционные тесты

### Тест запуска системы

```python
# tests/integration/test_start_integration.py
import pytest
from unittest.mock import patch
from app.core.engine import NeuroCrewLab

@pytest.mark.asyncio
async def test_system_startup():
    """Тест запуска всей системы."""
    with patch('app.config.Config.get_role_sequence') as mock_roles:
        mock_roles.return_value = [
            Mock(
                role_name="test_role",
                agent_type="test_connector",
                cli_command="test-cli",
                get_bot_token=Mock(return_value="test_token")
            )
        ]
        
        ncrew = NeuroCrewLab()
        
        # Проверка инициализации
        assert len(ncrew.roles) == 1
        assert ncrew.roles[0].role_name == "test_role"
        assert ncrew.is_role_based is True

@pytest.mark.asyncio
async def test_full_message_processing():
    """Тест полной обработки сообщения."""
    with patch('app.config.Config.get_role_sequence') as mock_roles:
        # Создание мокированной роли
        mock_role = Mock()
        mock_role.role_name = "test_role"
        mock_role.agent_type = "test_connector"
        mock_role.cli_command = "test-cli"
        mock_role.get_bot_token.return_value = "test_token"
        mock_roles.return_value = [mock_role]
        
        ncrew = NeuroCrewLab()
        
        # Мокирование коннектора
        with patch('app.connectors.get_connector_class') as mock_get_class:
            mock_connector_class = Mock()
            mock_connector = Mock()
            mock_connector.execute = AsyncMock(return_value="Test response")
            mock_connector_class.return_value = mock_connector
            mock_get_class.return_value = mock_connector_class
            
            # Тест обработки сообщения
            responses = []
            chat_id = 123456
            message = "Test message"
            
            async for response in ncrew.handle_message(chat_id, message):
                responses.append(response)
            
            assert len(responses) > 0
            assert "Test response" in responses[0]
```

### Тест веб-сервера

```python
# tests/interfaces/test_web_server.py
import pytest
from unittest.mock import Mock, patch
from app.interfaces.web_server import app

@pytest.fixture
def client():
    """Тестовый клиент Flask."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    """Тест health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    
    data = response.get_json()
    assert data['status'] == 'healthy'
    assert 'timestamp' in data

def test_index_unauthorized(client):
    """Тест доступа без аутентификации."""
    response = client.get('/')
    assert response.status_code == 401

def test_index_authorized(client):
    """Тест доступа с аутентификацией."""
    import base64
    
    # Basic Auth credentials
    credentials = base64.b64encode(b'admin:password').decode('utf-8')
    headers = {'Authorization': f'Basic {credentials}'}
    
    with patch('app.interfaces.web_server.Config.WEB_ADMIN_USER', 'admin'), \
         patch('app.interfaces.web_server.Config.WEB_ADMIN_PASS', 'password'):
        
        response = client.get('/', headers=headers)
        assert response.status_code == 200
        assert b'NeuroCrew Lab' in response.data

def test_save_roles(client):
    """Тест сохранения ролей."""
    import base64
    
    credentials = base64.b64encode(b'admin:password').decode('utf-8')
    headers = {'Authorization': f'Basic {credentials}'}
    
    role_data = {
        'roles[0][role_name]': 'test_role',
        'roles[0][display_name]': 'Test Role',
        'roles[0][telegram_bot_name]': 'Test_Role_Bot',
        'roles[0][system_prompt_file]': 'test.md',
        'roles[0][agent_type]': 'test_connector',
        'roles[0][cli_command]': 'test-cli'
    }
    
    with patch('app.interfaces.web_server.Config.WEB_ADMIN_USER', 'admin'), \
         patch('app.interfaces.web_server.Config.WEB_ADMIN_PASS', 'password'), \
         patch('app.interfaces.web_server.validate_and_save_roles') as mock_save:
        
        mock_save.return_value = True
        
        response = client.post('/save', data=role_data, headers=headers)
        assert response.status_code == 200
        
        data = response.get_json()
        assert data['success'] is True
```

## End-to-End тесты

### Тест Telegram потока

```python
# tests/e2e/test_telegram_flow.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from telegram import Update, Message, User, Chat
from app.interfaces.telegram_bot import TelegramBot

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_full_telegram_flow():
    """Тест полного потока в Telegram."""
    # Создание мокированного обновления
    mock_update = Mock(spec=Update)
    mock_message = Mock(spec=Message)
    mock_user = Mock(spec=User)
    mock_chat = Mock(spec=Chat)
    
    mock_user.id = 123456
    mock_user.username = "testuser"
    mock_chat.id = -1001234567890  # Target chat ID
    mock_message.text = "Create a REST API"
    mock_message.from_user = mock_user
    mock_message.chat = mock_chat
    mock_update.message = mock_message
    
    # Мокирование бота
    mock_bot = AsyncMock()
    
    with patch('app.config.Config.TARGET_CHAT_ID', -1001234567890), \
         patch('app.interfaces.telegram_bot.Bot') as mock_bot_class, \
         patch('app.core.engine.NeuroCrewLab') as mock_ncrew_class:
        
        mock_bot_class.return_value = mock_bot
        mock_ncrew = AsyncMock()
        mock_ncrew.handle_message = AsyncMock(return_value=iter(["API created successfully"]))
        mock_ncrew_class.return_value = mock_ncrew
        
        # Создание Telegram бота
        telegram_bot = TelegramBot()
        telegram_bot.bot = mock_bot
        
        # Обработка сообщения
        await telegram_bot.handle_message(mock_update, None)
        
        # Проверки
        mock_ncrew.handle_message.assert_called_once_with(
            -1001234567890, 
            "Create a REST API"
        )
        
        # Проверка отправки ответа
        mock_bot.send_message.assert_called()
```

## Тестирование производительности

### Нагрузочные тесты

```python
# tests/performance/test_load.py
import pytest
import asyncio
import time
from app.core.engine import NeuroCrewLab

@pytest.mark.asyncio
@pytest.mark.slow
async def test_concurrent_message_processing():
    """Тест одновременной обработки сообщений."""
    ncrew = NeuroCrewLab()
    
    # Мокирование коннекторов для быстрого выполнения
    with patch('app.connectors.get_connector_class') as mock_get_class:
        mock_connector_class = Mock()
        mock_connector = Mock()
        mock_connector.execute = AsyncMock(return_value="Quick response")
        mock_connector_class.return_value = mock_connector
        mock_get_class.return_value = mock_connector_class
        
        # Создание множества одновременных запросов
        async def process_message(chat_id, message):
            responses = []
            async for response in ncrew.handle_message(chat_id, message):
                responses.append(response)
            return responses
        
        # Запуск 10 одновременных запросов
        tasks = []
        for i in range(10):
            task = asyncio.create_task(
                process_message(123456 + i, f"Message {i}")
            )
            tasks.append(task)
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # Проверки
        assert len(results) == 10
        assert all(len(result) > 0 for result in results)
        assert end_time - start_time < 5.0  # Должно выполниться за 5 секунд

@pytest.mark.asyncio
@pytest.mark.slow
async def test_memory_usage():
    """Тест использования памяти."""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss
    
    ncrew = NeuroCrewLab()
    
    # Обработка большого количества сообщений
    for i in range(100):
        await ncrew.storage.add_message(
            chat_id=123456,
            role_name="user",
            content=f"Long message {i} " * 100,  # Увеличиваем размер
            message_type="user_message"
        )
    
    final_memory = process.memory_info().rss
    memory_increase = final_memory - initial_memory
    
    # Проверка, что память не выросла более чем на 50MB
    assert memory_increase < 50 * 1024 * 1024
```

## CI/CD интеграция

### GitHub Actions

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: [3.10, 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov
    
    - name: Run unit tests
      run: |
        pytest tests/unit/ -v --cov=app --cov-report=xml
    
    - name: Run integration tests
      run: |
        pytest tests/integration/ -v
    
    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella
```

### Локальный pre-commit hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
  
  - repo: https://github.com/psf/black
    rev: 22.10.0
    hooks:
      - id: black
        language_version: python3
  
  - repo: https://github.com/pycqa/isort
    rev: 5.11.4
    hooks:
      - id: isort
        args: ["--profile", "black"]
  
  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
        args: [tests/unit/]
```

## Метрики и отчетность

### Покрытие кода

```bash
# Генерация отчета о покрытии
pytest --cov=app --cov-report=html --cov-report=term

# Проверка минимального покрытия
pytest --cov=app --cov-fail-under=80
```

### Анализ производительности тестов

```bash
# Установка плагина для профилирования
pip install pytest-profiling

# Запуск с профилированием
pytest --profile

# Анализ самых медленных тестов
pytest --durations=10
```

### Тестовая документация

```python
# Пример документированного теста
def test_user_authentication():
    """
    Тест аутентификации пользователя.
    
    Scenario:
    1. Пользователь вводит правильные credentials
    2. Система возвращает токен доступа
    3. Токен может быть использован для доступа к защищенным ресурсам
    
    Expected Result:
    - Статус код 200
    - Валидный JWT токен в ответе
    """
    pass
```

## Лучшие практики

### Организация тестов

1. **Структура:** Group related tests in the same module
2. **Именование:** Use descriptive test names that explain what is being tested
3. **Изоляция:** Tests should be independent and not rely on each other
4. **Мокирование:** Mock external dependencies to ensure tests are reliable
5. **Очистка:** Use fixtures to set up and tear down test environments

### Асинхронные тесты

```python
# Правильный паттерн для асинхронных тестов
@pytest.mark.asyncio
async def test_async_operation():
    # Arrange
    async_resource = await setup_async_resource()
    
    # Act
    result = await async_resource.do_something()
    
    # Assert
    assert result.is_success()
    await cleanup_async_resource(async_resource)
```

### Обработка ошибок

```python
# Тестирование исключений
def test_invalid_input_raises_error():
    with pytest.raises(ValueError, match="Invalid input"):
        process_invalid_input("bad data")

# Тестирование предупреждений
def test_deprecation_warning():
    with pytest.warns(DeprecationWarning):
        use_deprecated_function()
```

### Параметризованные тесты

```python
# Тестирование множества сценариев
@pytest.mark.parametrize("input,expected", [
    ("valid@email.com", True),
    ("invalid-email", False),
    ("", False),
    ("test@domain.co.uk", True)
])
def test_email_validation(input, expected):
    assert validate_email(input) == expected
```