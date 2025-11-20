# 💾 Файловое хранилище NeuroCrew Lab

## Обзор

Файловое хранилище обеспечивает **асинхронное сохранение истории диалогов** в JSON-формате с поддержкой метаданных, бэкапов и автоматической очистки. Реализовано в `app/storage/file_storage.py` и работает с директорией `data/conversations/`.

## Структура хранения

### Директории

```
data/
├── conversations/          # Основное хранилище диалогов
│   ├── chat_123456789.json     # История чата
│   ├── chat_-100123456789.json  # История группы
│   └── ...
├── backups/               # Бэкапы поврежденных файлов
│   ├── chat_123456789.json.backup.20231120_143022
│   └── ...
└── logs/                  # Логи приложения
    └── ncrew.log
```

### Формат файла диалога

```json
{
  "chat_id": 123456789,
  "created_at": "2023-11-20T14:30:22.123456Z",
  "updated_at": "2023-11-20T15:45:10.654321Z",
  "message_count": 25,
  "metadata": {
    "last_role_index": 2,
    "total_responses": 18,
    "errors_count": 1
  },
  "messages": [
    {
      "timestamp": "2023-11-20T14:30:22.123456Z",
      "role_name": "user",
      "message_type": "user_message",
      "content": "Создай REST API для управления задачами",
      "metadata": {
        "message_id": 1,
        "user_id": 987654321,
        "username": "john_doe"
      }
    },
    {
      "timestamp": "2023-11-20T14:31:45.234567Z",
      "role_name": "software_developer",
      "message_type": "agent_response",
      "content": "Создаю REST API с использованием FastAPI...",
      "metadata": {
        "message_id": 2,
        "agent_type": "gemini_acp",
        "execution_time": 8.5,
        "tokens_used": 156
      }
    }
  ]
}
```

## Класс FileStorage

### Инициализация

```python
from app.storage.file_storage import FileStorage

storage = FileStorage()

# Или с кастомной директорией
storage = FileStorage(data_dir=Path("/custom/path"))
```

### Основные методы

#### add_message()

Добавление нового сообщения в историю диалога.

```python
async def add_message(
    self,
    chat_id: int,
    role_name: str,
    content: str,
    message_type: str = "user_message",
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """Добавление сообщения в историю."""
```

**Параметры:**
- `chat_id` - ID чата
- `role_name` - имя роли (user, software_developer, и т.д.)
- `content` - содержимое сообщения
- `message_type` - тип сообщения (`user_message`, `agent_response`, `system_message`)
- `metadata` - дополнительные метаданные

**Пример использования:**
```python
await storage.add_message(
    chat_id=123456789,
    role_name="software_developer",
    content="Я создам REST API с использованием FastAPI...",
    message_type="agent_response",
    metadata={
        "agent_type": "gemini_acp",
        "execution_time": 8.5,
        "tokens_used": 156
    }
)
```

#### load_conversation()

Загрузка истории диалога.

```python
async def load_conversation(
    self,
    chat_id: int,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """Загрузка истории диалога."""
```

**Пример:**
```python
conversation = await storage.load_conversation(chat_id=123456789)
messages = conversation.get("messages", [])
```

#### get_recent_messages()

Получение последних N сообщений.

```python
async def get_recent_messages(
    self,
    chat_id: int,
    count: int = 10,
    role_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Получение последних сообщений."""
```

**Пример:**
```python
# Последние 10 сообщений всех ролей
recent = await storage.get_recent_messages(chat_id=123456789, count=10)

# Последние 5 сообщений конкретной роли
dev_messages = await storage.get_recent_messages(
    chat_id=123456789, 
    count=5, 
    role_name="software_developer"
)
```

#### clear_conversation()

Очистка истории диалога.

```python
async def clear_conversation(self, chat_id: int) -> None:
    """Очистка истории чата."""
```

#### get_conversation_stats()

Получение статистики по диалогу.

```python
async def get_conversation_stats(self, chat_id: int) -> Dict[str, Any]:
    """Получение статистики диалога."""
```

**Возвращает:**
```json
{
  "message_count": 25,
  "role_counts": {
    "user": 5,
    "software_developer": 8,
    "code_review": 7,
    "product_owner": 5
  },
  "first_message": "2023-11-20T14:30:22.123456Z",
  "last_message": "2023-11-20T15:45:10.654321Z",
  "total_execution_time": 145.7,
  "average_response_time": 7.3
}
```

## Управление бэкапами

### Создание бэкапов

Перед каждым сохранением основной файл копируется в бэкап:

```python
async def _backup_conversation_file(self, chat_id: int, file_path: Path) -> None:
    """Создание бэкапа файла диалога."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = self.backups_dir / f"{file_path.stem}.backup.{timestamp}"
    
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Backup created: {backup_path}")
    except Exception as e:
        logger.error(f"Backup failed: {e}")
```

### Очистка старых бэкапов

```python
async def cleanup_old_backups(self, max_age_days: int = 7) -> int:
    """Очистка старых бэкапов."""
    cutoff_time = datetime.utcnow() - timedelta(days=max_age_days)
    cleaned_count = 0
    
    for backup_file in self.backups_dir.glob("*.backup.*"):
        try:
            file_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
            if file_time < cutoff_time:
                backup_file.unlink()
                cleaned_count += 1
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_file}: {e}")
    
    return cleaned_count
```

### Восстановление из бэкапа

```python
async def restore_from_backup(
    self, 
    chat_id: int, 
    backup_timestamp: Optional[str] = None
) -> bool:
    """Восстановление из бэкапа."""
    
    # Поиск последнего бэкапа
    if backup_timestamp:
        backup_file = self.backups_dir / f"chat_{chat_id}.backup.{backup_timestamp}"
    else:
        # Найти последний бэкап
        backup_files = list(self.backups_dir.glob(f"chat_{chat_id}.backup.*"))
        if not backup_files:
            return False
        backup_file = max(backup_files, key=lambda f: f.stat().st_mtime)
    
    # Восстановление
    try:
        target_file = self.conversations_dir / f"chat_{chat_id}.json"
        shutil.copy2(backup_file, target_file)
        logger.info(f"Restored chat {chat_id} from backup")
        return True
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return False
```

## Метаданные сообщений

### Стандартные метаданные

#### Для пользовательских сообщений

```json
{
  "message_id": 1,
  "user_id": 987654321,
  "username": "john_doe",
  "first_name": "John",
  "last_name": "Doe"
}
```

#### Для ответов агентов

```json
{
  "message_id": 2,
  "agent_type": "gemini_acp",
  "execution_time": 8.5,
  "tokens_used": 156,
  "retry_count": 0,
  "connector_session_id": "chat_123456789_software_developer"
}
```

#### Для системных сообщений

```json
{
  "message_id": 3,
  "system_event": "role_cycle_completed",
  "role_sequence": ["software_developer", "code_review", "product_owner"],
  "cycle_duration": 45.2
}
```

### Расширенные метаданные

```python
# Добавление пользовательских метаданных
await storage.add_message(
    chat_id=123456789,
    role_name="software_developer",
    content="Код создан успешно",
    message_type="agent_response",
    metadata={
        "agent_type": "gemini_acp",
        "execution_time": 8.5,
        "tokens_used": 156,
        "code_blocks_count": 3,
        "files_created": ["api.py", "models.py", "schemas.py"],
        "technologies": ["FastAPI", "SQLAlchemy", "Pydantic"],
        "confidence_score": 0.95,
        "debug_info": {
            "cli_command": "gemini --experimental-acp",
            "process_id": 12345,
            "memory_usage": "45MB"
        }
    }
)
```

## Ограничения и оптимизация

### Ограничение длины диалога

```python
async def _enforce_conversation_limit(
    self, 
    messages: List[Dict[str, Any]], 
    max_length: int
) -> List[Dict[str, Any]]:
    """Применение ограничения длины диалога."""
    
    if len(messages) <= max_length:
        return messages
    
    # Сохраняем системные сообщения и последние N сообщений
    system_messages = [msg for msg in messages if msg.get("message_type") == "system_message"]
    regular_messages = [msg for msg in messages if msg.get("message_type") != "system_message"]
    
    # Оставляем последние сообщения
    recent_messages = regular_messages[-max_length:]
    
    # Объединяем системные + последние
    return system_messages + recent_messages
```

### Асинхронная запись

```python
async def _write_conversation_async(
    self, 
    chat_id: int, 
    conversation_data: Dict[str, Any]
) -> None:
    """Асинхронная запись данных диалога."""
    
    file_path = self.conversations_dir / f"chat_{chat_id}.json"
    
    try:
        # Создание бэкапа
        if file_path.exists():
            await self._backup_conversation_file(chat_id, file_path)
        
        # Асинхронная запись
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(conversation_data, ensure_ascii=False, indent=2))
        
        logger.debug(f"Conversation saved: {file_path}")
        
    except Exception as e:
        logger.error(f"Failed to save conversation {chat_id}: {e}")
        raise
```

### Валидация данных

```python
def _validate_message_data(self, message: Dict[str, Any]) -> bool:
    """Валидация данных сообщения."""
    
    required_fields = ["timestamp", "role_name", "message_type", "content"]
    
    for field in required_fields:
        if field not in message:
            logger.error(f"Missing required field: {field}")
            return False
    
    # Валидация формата временной метки
    try:
        datetime.fromisoformat(message["timestamp"].replace('Z', '+00:00'))
    except ValueError:
        logger.error(f"Invalid timestamp format: {message['timestamp']}")
        return False
    
    # Валидация типа сообщения
    valid_types = ["user_message", "agent_response", "system_message"]
    if message["message_type"] not in valid_types:
        logger.error(f"Invalid message type: {message['message_type']}")
        return False
    
    return True
```

## Интеграция с оркестратором

### Использование в NeuroCrewLab

```python
class NeuroCrewLab:
    def __init__(self, storage: Optional[FileStorage] = None):
        self.storage = storage or FileStorage()
    
    async def handle_message(self, chat_id: int, message: str) -> AsyncGenerator[str, None]:
        """Обработка сообщения с сохранением в историю."""
        
        # Сохранение пользовательского сообщения
        await self.storage.add_message(
            chat_id=chat_id,
            role_name="user",
            content=message,
            message_type="user_message",
            metadata={"user_input": True}
        )
        
        # Обработка ролей
        for role in self.roles:
            # Формирование промпта из истории
            context = await self._build_context(chat_id, role)
            
            # Выполнение роли
            response = await self._process_with_role(role, context)
            
            if response and response != ".....":
                # Сохранение ответа агента
                await self.storage.add_message(
                    chat_id=chat_id,
                    role_name=role.role_name,
                    content=response,
                    message_type="agent_response",
                    metadata={
                        "agent_type": role.agent_type,
                        "execution_time": time.time() - start_time
                    }
                )
                
                yield response
```

### Построение контекста для роли

```python
async def _build_context(self, chat_id: int, role: RoleConfig) -> str:
    """Построение контекста для роли из истории."""
    
    # Получение сообщений с последнего участия роли
    messages = await self.storage.get_messages_since_last_role_participation(
        chat_id=chat_id,
        role_name=role.role_name
    )
    
    # Формирование промпта
    context_parts = [role.system_prompt]
    
    for msg in messages:
        if msg["role_name"] == "user":
            context_parts.append(f"User: {msg['content']}")
        else:
            context_parts.append(f"{msg['role_name']}: {msg['content']}")
    
    return "\n\n".join(context_parts)
```

## Мониторинг и метрики

### Статистика использования

```python
async def get_storage_stats(self) -> Dict[str, Any]:
    """Получение статистики хранилища."""
    
    stats = {
        "total_conversations": 0,
        "total_messages": 0,
        "total_size_bytes": 0,
        "backup_count": 0,
        "oldest_conversation": None,
        "newest_conversation": None
    }
    
    # Подсчет диалогов
    for conv_file in self.conversations_dir.glob("chat_*.json"):
        stats["total_conversations"] += 1
        stats["total_size_bytes"] += conv_file.stat().st_size
        
        try:
            conv_data = await self._load_conversation_file(conv_file)
            stats["total_messages"] += len(conv_data.get("messages", []))
            
            created_at = conv_data.get("created_at")
            if created_at:
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                
                if not stats["oldest_conversation"] or created_dt < stats["oldest_conversation"]:
                    stats["oldest_conversation"] = created_dt
                
                if not stats["newest_conversation"] or created_dt > stats["newest_conversation"]:
                    stats["newest_conversation"] = created_dt
                    
        except Exception as e:
            logger.error(f"Failed to analyze {conv_file}: {e}")
    
    # Подсчет бэкапов
    stats["backup_count"] = len(list(self.backups_dir.glob("*.backup.*")))
    
    return stats
```

### Health checks

```python
async def health_check(self) -> Dict[str, Any]:
    """Проверка состояния хранилища."""
    
    checks = {
        "conversations_dir_exists": self.conversations_dir.exists(),
        "conversations_dir_writable": os.access(self.conversations_dir, os.W_OK),
        "backups_dir_exists": self.backups_dir.exists(),
        "backups_dir_writable": os.access(self.backups_dir, os.W_OK),
        "disk_space_available": self._check_disk_space(),
        "corrupted_files": await self._check_corrupted_files()
    }
    
    overall_healthy = all(checks.values())
    
    return {
        "healthy": overall_healthy,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }

def _check_disk_space(self) -> bool:
    """Проверка доступного дискового пространства."""
    stat = shutil.disk_usage(self.conversations_dir)
    # Минимум 100MB свободного места
    return stat.free > 100 * 1024 * 1024

async def _check_corrupted_files(self) -> int:
    """Проверка поврежденных файлов."""
    corrupted_count = 0
    
    for conv_file in self.conversations_dir.glob("chat_*.json"):
        try:
            async with aiofiles.open(conv_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                json.loads(content)  # Валидация JSON
        except Exception:
            corrupted_count += 1
    
    return corrupted_count
```

## Тестирование

### Unit-тесты

```python
import pytest
import tempfile
import asyncio
from pathlib import Path
from app.storage.file_storage import FileStorage

@pytest.fixture
async def temp_storage():
    """Временное хранилище для тестов."""
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = FileStorage(data_dir=Path(temp_dir))
        yield storage

@pytest.mark.asyncio
async def test_add_message(temp_storage):
    """Тест добавления сообщения."""
    await temp_storage.add_message(
        chat_id=123456,
        role_name="user",
        content="Test message",
        message_type="user_message"
    )
    
    conversation = await temp_storage.load_conversation(123456)
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["content"] == "Test message"

@pytest.mark.asyncio
async def test_conversation_limit(temp_storage):
    """Тест ограничения длины диалога."""
    # Добавление сообщений сверх лимита
    for i in range(150):  # Превышаем стандартный лимит
        await temp_storage.add_message(
            chat_id=123456,
            role_name="user",
            content=f"Message {i}",
            message_type="user_message"
        )
    
    conversation = await temp_storage.load_conversation(123456)
    assert len(conversation["messages"]) <= 100  # Стандартный лимит
```

### Интеграционные тесты

```python
@pytest.mark.asyncio
async def test_backup_and_restore(temp_storage):
    """Тест бэкапа и восстановления."""
    # Добавление сообщений
    await temp_storage.add_message(
        chat_id=123456,
        role_name="user",
        content="Original message",
        message_type="user_message"
    )
    
    # Изменение сообщения
    await temp_storage.add_message(
        chat_id=123456,
        role_name="agent",
        content="Modified message",
        message_type="agent_response"
    )
    
    # Восстановление из бэкапа
    restored = await temp_storage.restore_from_backup(123456)
    assert restored
    
    # Проверка восстановления
    conversation = await temp_storage.load_conversation(123456)
    assert len(conversation["messages"]) == 1
    assert conversation["messages"][0]["content"] == "Original message"
```

### Нагрузочное тестирование

```python
@pytest.mark.asyncio
async def test_concurrent_access(temp_storage):
    """Тест одновременного доступа."""
    async def add_messages(chat_id: int, count: int):
        for i in range(count):
            await temp_storage.add_message(
                chat_id=chat_id,
                role_name="user",
                content=f"Message {i}",
                message_type="user_message"
            )
    
    # Запуск нескольких задач одновременно
    tasks = [
        add_messages(123456, 50),
        add_messages(123457, 50),
        add_messages(123458, 50)
    ]
    
    await asyncio.gather(*tasks)
    
    # Проверка результатов
    for chat_id in [123456, 123457, 123458]:
        conversation = await temp_storage.load_conversation(chat_id)
        assert len(conversation["messages"]) == 50
```