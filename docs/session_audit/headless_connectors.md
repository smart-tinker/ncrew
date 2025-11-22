# Headless Connectors Session Audit

**Дата:** 21 ноября 2024  
**Цель:** Анализ управления сессиями и истории в non-ACP коннекторах (`claude_cli_connector.py`, `codex_cli_connector.py`)

---

## Executive Summary

Headless коннекторы (Claude CLI и Codex CLI) используют **stateless subprocess model** в отличие от ACP коннекторов, которые управляют долгоживущими процессами. Ключевая разница:

- **ACP коннекторы**: Один долгоживущий процесс с bidirectional stdin/stdout, история управляется в Python
- **Headless коннекторы**: Каждый вызов - новый subprocess, история управляется **полностью на стороне CLI** через session identifiers

Это создаёт **критическую зависимость от внешнего state management** и несколько рисков для continuous-session поведения.

---

## 1. Claude CLI Connector

### 1.1 Session Management

**Механизм идентификации сессии:**
```python
# В launch():
self.session_id = str(uuid.uuid4())  # Генерируется локально
self._session_created = False        # Флаг успешного создания
```

**CLI флаги:**
- **Первый вызов**: `--session-id <uuid>` - создаёт новую сессию в Claude CLI
- **Последующие вызовы**: `--resume <uuid>` - продолжает существующую сессию
- **Переключение**: Происходит после первого успешного returncode==0

**Пример конструирования команды:**
```python
if self._session_created:
    args += ["--resume", self.session_id]
else:
    args += ["--session-id", self.session_id]
args.append(prompt)  # Только дельта, не вся история
```

### 1.2 History Management

**Передача контекста:**
- ❌ **НЕ передаёт полную историю**
- ✅ **Передаёт только DELTA** (новый промпт)
- 🔄 **История хранится на стороне Claude CLI**, привязана к session_id

**Цитата из кода:**
```python
async def execute(self, delta_prompt: str) -> str:
    # Передаёт ТОЛЬКО новый промпт, не историю
    response = await self._run_claude(prompt)
```

### 1.3 Process Model

**Критическое отличие от базового класса:**
```python
class BaseConnector(ABC):
    def __init__(self):
        self.process: Optional[asyncio.subprocess.Process] = None  # ❌ НЕ используется в Claude
```

**Реальное поведение:**
```python
async def _run_claude(self, prompt: str) -> str:
    # 1. Создаём новый процесс
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=2 * 1024 * 1024,
    )
    # 2. Ждём завершения
    stdout, stderr = await process.communicate()
    # 3. Процесс умирает
    # 4. Сессия ЖИВЁТ в Claude CLI, не в Python
```

**Каждый вызов execute() создаёт и убивает subprocess.**

### 1.4 Session Priming

**Когда происходит:**
```python
async def launch(self, command: str, system_prompt: str):
    self.session_id = str(uuid.uuid4())
    self._initialized = True
    self._session_created = False
    await self._prime_session()  # ← Сразу после инициализации
```

**Что делает priming:**
```python
async def _prime_session(self):
    if not self.system_prompt:
        return
    primer = (
        f"{self.system_prompt}\n\n"
        f"Confirm readiness with the single word READY."
    )
    try:
        await self._run_claude(primer)
    except Exception:
        pass  # ⚠️ ИГНОРИРУЕТ ошибки!
```

**Риск:** Если прайминг провалился, но не выбросил exception, сессия может быть в inconsistent state.

### 1.5 Failure Handling

**При ошибке CLI:**
```python
if process.returncode != 0:
    error = stderr.decode().strip() or stdout.decode().strip()
    # ❌ СРАЗУ RuntimeError, НЕТ retry логики
    raise RuntimeError(f"Claude CLI failed: {error}")
```

**При потере сессии:**
```python
# Комментарий в коде:
# "Handle specific case where session might be locked but we want to force usage
#  OR if --resume fails because session was lost/cleaned up"
# Но для now, let's just report the error to be safe.
```

**⚠️ НЕТ механизма восстановления после потери сессии на стороне CLI.**

### 1.6 Reset/Shutdown Behavior

**При reset:**
```python
async def shutdown(self):
    self.session_id = None
    self._initialized = False
    self._session_created = False
    # ❌ НЕ очищает сессию на стороне CLI
    # ❌ НЕ убивает процесс (его нет)
```

**Влияние на continuity:**
- Session ID теряется навсегда
- Следующий `launch()` создаст НОВЫЙ session_id
- Старая сессия может остаться в CLI (если CLI не чистит автоматически)

### 1.7 State Machine

```
[IDLE]
   ↓
launch(command, system_prompt)
   → session_id = uuid4()
   → _initialized = True
   → _session_created = False
   ↓
_prime_session()
   → _run_claude(system_prompt + "READY")
   → использует --session-id <uuid>
   → если returncode==0: _session_created=True
   ↓
[PRIMED]
   ↓
execute(delta_prompt)  ← Может вызываться N раз
   → _run_claude(delta_prompt)
   → использует --resume <uuid> (если _session_created)
   → если returncode==0: продолжаем
   → если returncode!=0: RuntimeError
   ↓
[ACTIVE SESSION]
   ↓
shutdown()
   → session_id = None
   → _initialized = False
   ↓
[IDLE]

Параллельная жизнь сессии в CLI:
--session-id → создаётся в CLI
--resume     → используется в CLI
??? → когда CLI очищает сессию (timeout? manual cleanup?)
```

### 1.8 Test Coverage Analysis

**Из `test_claude_cli_connector.py`:**
```python
# Mock скрипт принимает --session-id
parser.add_argument("--session-id", dest="session_id")
# ❌ НЕТ тестирования --resume
# ❌ НЕТ тестирования session loss
# ❌ НЕТ тестирования recovery после ошибок

# Тест проверяет:
response1 = await connector.execute("Ping")
response2 = await connector.execute("Pong")
# ✅ Проверяет что session_id сохраняется между вызовами
# ❌ Но mock всегда возвращает успех
```

---

## 2. Codex CLI Connector

### 2.1 Session Management

**Механизм идентификации сессии:**
```python
# В launch():
self.thread_id: str | None = None  # ❌ НЕ генерируется локально
                                   # ✅ Получается от CLI
```

**CLI флаги:**
- **Первый вызов**: `codex exec --json prompt` - CLI возвращает thread_id в JSON
- **Последующие вызовы**: `codex exec --json resume <thread_id> prompt`
- **Отличие от Claude**: thread_id контролируется CLI, не Python

**Пример конструирования команды:**
```python
args: List[str] = shlex.split(self.base_command)  # "codex exec --json ..."
if resume and self.thread_id:
    args += ["resume", self.thread_id, prompt]
else:
    args.append(prompt)
```

### 2.2 History Management

**Передача контекста:**
- ❌ **НЕ передаёт полную историю**
- ✅ **Передаёт только DELTA** (новый промпт)
- 🔄 **История хранится на стороне Codex CLI**, привязана к thread_id

**Извлечение thread_id из ответа:**
```python
event_type = event.get("type")
if event_type == "thread.started":
    thread_id = event.get("thread_id")
    if thread_id:
        self.thread_id = thread_id  # Сохраняем для следующих вызовов
```

### 2.3 Process Model

**Аналогично Claude - stateless subprocess:**
```python
async def _run_codex(self, prompt: str, resume: bool) -> str:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=2 * 1024 * 1024,
    )
    stdout, stderr = await process.communicate()
    # Процесс завершается здесь
```

**BaseConnector.process НЕ используется.**

### 2.4 Session Priming

**Двойной прайминг:**
```python
async def launch(self, command: str, system_prompt: str):
    self.thread_id = None
    self._initialized = True
    await self._prime_session()  # Прайминг #1

async def execute(self, delta_prompt: str) -> str:
    if not self.thread_id:
        # ⚠️ Прайминг #2 - если thread_id потерян
        await self._prime_session()
    response = await self._run_codex(prompt, resume=bool(self.thread_id))
```

**Логика прайминга:**
```python
async def _prime_session(self):
    if not self.system_prompt:
        return
    primer = (
        f"{self.system_prompt}\n\n"
        f"You are being initialized by an orchestrator. Respond with READY."
    )
    try:
        await self._run_codex(primer, resume=False)
    except Exception:
        # ⚠️ ИГНОРИРУЕТ ошибки
        # We only care about establishing the thread id
        pass
```

**Важное отличие:** Даже если прайминг провалился, thread_id мог быть установлен из JSON events.

### 2.5 Failure Handling

**При ошибке CLI:**
```python
if process.returncode != 0:
    error_msg = stderr.decode().strip() or stdout.decode().strip()
    # Попытка парсить JSON error
    try:
        for line in error_msg.splitlines():
            if line.strip().startswith("{"):
                err_json = json.loads(line)
                if err_json.get("type") == "error":
                    error_msg = err_json.get("error", error_msg)
    except:
        pass
    # ❌ СРАЗУ RuntimeError
    raise RuntimeError(f"Codex CLI failed: {error_msg}")
```

**При потере thread:**
- `execute()` проверяет `if not self.thread_id` и вызывает `_prime_session()`
- Это создаст НОВЫЙ thread, а не продолжит старый
- **Потеря контекста без уведомления**

### 2.6 Reset/Shutdown Behavior

**При reset:**
```python
async def shutdown(self):
    self.thread_id = None
    self._initialized = False
    # ❌ НЕ очищает thread на стороне CLI
```

**Влияние на continuity:**
- thread_id теряется
- Следующий `execute()` создаст новый thread через `_prime_session()`
- Старый thread остаётся в CLI (orphaned)

### 2.7 State Machine

```
[IDLE]
   ↓
launch(command, system_prompt)
   → thread_id = None
   → _initialized = True
   ↓
_prime_session()
   → _run_codex(system_prompt + "READY", resume=False)
   → CLI возвращает thread_id в JSON event "thread.started"
   → thread_id сохраняется
   ↓
[PRIMED with thread_id]
   ↓
execute(delta_prompt)
   → if thread_id is None:  # ⚠️ Recovery механизм
   │    _prime_session()  # Создаёт НОВЫЙ thread
   ↓
   → _run_codex(delta_prompt, resume=True)
   → CLI продолжает thread
   ↓
[ACTIVE THREAD]
   ↓
shutdown()
   → thread_id = None
   ↓
[IDLE]

Жизненный цикл thread в CLI:
"thread.started" → CLI создаёт thread
resume <thread_id> → CLI использует thread
??? → когда CLI удаляет thread (неясно)
```

### 2.8 Test Coverage Analysis

**Из `test_codex_cli_connector.py`:**
```python
# Mock скрипт обрабатывает resume:
if args[0] == "resume":
    thread_id = args[1]
    prompt = args[2]
    prefix = "Resume"
else:
    thread_id = str(uuid.uuid4())
    prompt = args[0]
    prefix = "Init"

# Тест проверяет:
first = await connector.execute("Hello")
assert "Echo [Resume " in first  # ✅ Первый execute уже Resume
# Потому что _prime_session создал thread

second = await connector.execute("World")
assert f"Echo [Resume {thread_id}]: World" == second
# ✅ Проверяет что thread_id сохраняется
```

**Покрытие:**
- ✅ Тестирует создание thread
- ✅ Тестирует resume механизм
- ❌ НЕТ тестирования потери thread
- ❌ НЕТ тестирования recovery после ошибок

---

## 3. Сравнение с ACP Коннекторами

### 3.1 Архитектурные различия

| Aspect | ACP Connectors | Headless Connectors |
|--------|----------------|---------------------|
| **Process Lifetime** | Долгоживущий (от launch до shutdown) | Эпизодический (создаётся для каждого execute) |
| **Communication** | Bidirectional stdin/stdout | One-shot subprocess call |
| **History Storage** | Может быть в Python | Полностью на стороне CLI |
| **Session ID** | Опционально (часть протокола) | Критически важен |
| **BaseConnector.process** | ✅ Используется | ❌ НЕ используется |
| **Context Management** | Контролируется Python | Контролируется CLI |

### 3.2 Пример ACP (для контраста)

```python
# OpenCode ACP Connector:
async def launch(self, command: str, system_prompt: str):
    self.process = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE,   # ← Bidirectional
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Процесс продолжает жить

async def execute(self, delta_prompt: str) -> str:
    # Используем СУЩЕСТВУЮЩИЙ процесс
    await self._send_request(delta_prompt)
    response = await self._read_response()
    return response
    # Процесс всё ещё жив
```

---

## 4. Integration with NeuroCrew Engine

### 4.1 Как Engine использует коннекторы

**Из `app/core/engine.py`:**

```python
def _get_or_create_role_connector(self, chat_id: int, role):
    """Создаёт или переиспользует connector для роли."""
    key = (chat_id, role.role_name)
    connector = self.connector_sessions.get(key)
    
    if connector:
        if connector.is_alive():  # ← Для headless всегда True если _initialized
            return connector
        # Connector died, remove so we can recreate
        del self.connector_sessions[key]
        # ⚠️ Сброс индекса истории
        self.role_last_seen_index[key] = 0
    
    connector = self._create_connector_for_role(role)
    self.connector_sessions[key] = connector
    return connector
```

**Проблема:** `is_alive()` у headless коннекторов просто возвращает `_initialized`, не проверяя жив ли session на стороне CLI.

### 4.2 History Management в Engine

**Формирование промпта:**
```python
def _format_conversation_for_role(
    self, new_messages: List[Dict], role: RoleConfig, chat_id: int
) -> Tuple[str, bool]:
    """Build role prompt from messages that appeared since the role's last response."""
    
    # Берёт только НОВЫЕ сообщения с последнего вызова роли
    key = (chat_id, role.role_name)
    last_seen_index = self.role_last_seen_index.get(key, 0)
    new_messages = conversation[last_seen_index:]
    
    # Форматирует в текст
    context_lines = []
    for msg in new_messages:
        if msg.get("role") == "user":
            context_lines.append(f"User: {msg['content']}")
        elif msg.get("role") == "agent":
            context_lines.append(f"Assistant ({role_name}): {msg['content']}")
    
    prompt = "\n\n".join(context_lines)
    return prompt, True
```

**Критический момент:**
- Engine передаёт только ДЕЛЬТУ (новые сообщения) в `execute()`
- Headless коннекторы полагаются на CLI для хранения полной истории
- **Если CLI потеряет сессию, контекст будет утерян навсегда**

### 4.3 Reset Behavior в Engine

**При `/reset`:**
```python
async def _reset_chat_role_sessions(self, chat_id: int) -> None:
    """Reset (shutdown) all stateful role sessions for a specific chat."""
    for key in connector_keys:
        connector = self.connector_sessions.pop(key, None)
        if connector:
            await connector.shutdown()  # ← Для headless: просто None-ит session_id
```

**Последствия:**
1. `shutdown()` очищает `session_id` / `thread_id`
2. CLI сессия может остаться живой (orphaned)
3. Следующий `launch()` создаст НОВУЮ сессию
4. Старый контекст потерян

---

## 5. Protocol Notes

### 5.1 Claude CLI Protocol

**Output Format: `stream-json`**
```json
{"type": "system", "session_id": "uuid"}
{"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}]}}
{"type": "result", "is_error": false}
```

**Session Events:**
- `--session-id <uuid>`: Создаёт новую сессию
- `--resume <uuid>`: Продолжает существующую сессию
- Сессия хранится на стороне CLI (локально или в облаке - неясно из кода)

**Flags в коннекторе:**
```python
DEFAULT_COMMAND = (
    "claude -p --output-format stream-json --permission-mode bypassPermissions "
    "--dangerously-skip-permissions --verbose"
)
```

**Неясные моменты:**
- Как долго CLI хранит сессии?
- Есть ли автоматический cleanup?
- Что происходит при session lock?

### 5.2 Codex CLI Protocol

**Output Format: `--json`**
```json
{"type": "thread.started", "thread_id": "uuid"}
{"type": "turn.started"}
{"type": "item.completed", "item": {"type": "agent_message", "text": "..."}}
{"type": "turn.completed"}
```

**Thread Events:**
- Первый вызов: CLI генерирует thread_id и возвращает в `thread.started`
- `resume <thread_id> prompt`: Продолжает существующий thread
- Thread хранится на стороне CLI

**Flags в коннекторе:**
```python
DEFAULT_COMMAND = (
    "codex exec --json --full-auto --sandbox workspace-write --skip-git-repo-check"
)
```

**Неясные моменты:**
- Как долго CLI хранит threads?
- Есть ли limit на количество threads?
- Что происходит при истечении thread?

### 5.3 Отсутствующая документация

**Из README.md и AGENTS.md:**
- ✅ Есть инструкции по установке CLI
- ✅ Есть команды для авторизации (`codex login`, `claude setup-token`)
- ❌ НЕТ документации по lifetime сессий/threads
- ❌ НЕТ информации о cleanup политиках
- ❌ НЕТ руководства по recovery после потери сессии

**Рекомендация:** Запустить `claude --help` и `codex exec --help` для получения полной документации флагов.

---

## 6. Concrete Risks & Gaps

### 6.1 Critical Risks

#### 🔴 **Risk 1: Silent Session Loss**
- **Описание**: CLI может очистить сессию (timeout, restart, manual cleanup), но коннектор не узнает об этом
- **Последствия**: Следующий `execute()` вернёт ошибку или создаст новую сессию, потеряв контекст
- **Вероятность**: Средняя (зависит от CLI политик)
- **Impact**: Высокий (потеря контекста диалога)

#### 🔴 **Risk 2: No Session Verification**
- **Описание**: Коннекторы не проверяют валидность session_id/thread_id перед использованием
- **Последствия**: Ошибки обнаруживаются только после попытки resume
- **Вероятность**: Высокая
- **Impact**: Средний (requires manual intervention)

#### 🔴 **Risk 3: No Fallback Recovery**
- **Описание**: При ошибке `--resume`, коннектор выбрасывает RuntimeError вместо создания новой сессии
- **Последствия**: Роль становится недоступной до ручного reset
- **Вероятность**: Средняя
- **Impact**: Высокий (breaks dialogue flow)

### 6.2 Design Gaps

#### 🟡 **Gap 1: Process Model Mismatch**
- **Описание**: `BaseConnector` имеет `self.process`, но headless коннекторы его не используют
- **Последствия**: `is_alive()` не отражает реальное состояние сессии на стороне CLI
- **Рекомендация**: Добавить метод `is_session_valid()` в BaseConnector

#### 🟡 **Gap 2: History Not Stored Locally**
- **Описание**: Engine передаёт только дельты, полагаясь на CLI для хранения полной истории
- **Последствия**: Невозможно восстановить контекст после потери сессии
- **Рекомендация**: Опционально хранить историю в коннекторе для recovery

#### 🟡 **Gap 3: Prime Session Failures Ignored**
- **Описание**: `_prime_session()` игнорирует все exceptions
- **Последствия**: Коннектор может быть в inconsistent state (инициализирован, но сессия не создана)
- **Рекомендация**: Логировать ошибки и устанавливать флаг `_prime_failed`

#### 🟡 **Gap 4: Orphaned Sessions in CLI**
- **Описание**: `shutdown()` не очищает сессию на стороне CLI
- **Последствия**: Накопление мёртвых сессий в CLI storage
- **Рекомендация**: Добавить команды для explicit session cleanup (если CLI поддерживает)

### 6.3 Testing Gaps

#### 🟠 **Test Gap 1: No Resume Failure Testing**
- **Описание**: Тесты не проверяют что происходит при ошибке `--resume`
- **Рекомендация**: Добавить mock, который провоцирует session loss

#### 🟠 **Test Gap 2: No Session Expiration Testing**
- **Описание**: Тесты не симулируют timeout сессии между вызовами
- **Рекомендация**: Добавить тест с задержкой между execute()

#### 🟠 **Test Gap 3: No Multi-Chat Testing**
- **Описание**: Тесты не проверяют изоляцию сессий между разными чатами
- **Рекомендация**: Тест с двумя chat_id и проверкой что сессии не смешиваются

---

## 7. Comparison Table: State Persistence

| Component | Claude CLI | Codex CLI | ACP Connectors |
|-----------|-----------|-----------|----------------|
| **Session ID Generation** | Python (UUID) | CLI (returned in JSON) | Protocol-specific |
| **Session ID Storage** | Python variable | Python variable | Python + Protocol |
| **History Storage** | CLI-side | CLI-side | Process memory |
| **Context Window** | Unknown (CLI-managed) | Unknown (CLI-managed) | Known (protocol spec) |
| **Session Lifetime** | Unknown (CLI policy) | Unknown (CLI policy) | Process lifetime |
| **Recovery on Loss** | ❌ No | ⚠️ Creates new (context loss) | ✅ Can replay from Python history |
| **Explicit Cleanup** | ❌ No | ❌ No | ✅ Process termination |
| **Session Verification** | ❌ No | ❌ No | ✅ Process alive check |

---

## 8. Recommendations

### 8.1 Short-term Fixes (MVP-compatible)

1. **Добавить логирование prime failures:**
   ```python
   async def _prime_session(self):
       try:
           await self._run_claude(primer)
       except Exception as e:
           self.logger.error(f"Prime session failed: {e}")
           self._prime_failed = True  # Новый флаг
   ```

2. **Улучшить is_alive() для headless:**
   ```python
   def is_alive(self) -> bool:
       return self._initialized and not self._prime_failed
   ```

3. **Добавить session validation в execute():**
   ```python
   async def execute(self, delta_prompt: str) -> str:
       if not self._initialized or not self.session_id:
           raise RuntimeError("Connector not properly initialized")
       # ... rest
   ```

### 8.2 Medium-term Improvements

1. **Retry logic для resume failures:**
   ```python
   async def _run_claude_with_retry(self, prompt: str) -> str:
       try:
           return await self._run_claude(prompt)
       except RuntimeError as e:
           if "--resume" in str(e) and "failed" in str(e):
               self.logger.warning("Session lost, creating new session")
               self._session_created = False
               self.session_id = str(uuid.uuid4())
               return await self._run_claude(prompt)
           raise
   ```

2. **Локальное хранение истории (fallback):**
   ```python
   class ClaudeCLICodeConnector(BaseConnector):
       def __init__(self):
           super().__init__()
           self._local_history: List[Dict] = []  # Backup
   ```

3. **Session heartbeat проверки:**
   ```python
   async def verify_session(self) -> bool:
       """Проверяет что сессия всё ещё валидна."""
       try:
           response = await self._run_claude("ping")
           return True
       except:
           return False
   ```

### 8.3 Long-term Architecture

1. **Унификация session management:**
   - Создать `SessionManager` класс для управления session lifecycle
   - Поддержка для разных backend (CLI-based, API-based)
   - Автоматический recovery и fallback

2. **Explicit session cleanup:**
   - Добавить CLI команды для удаления сессий (если поддерживается)
   - Периодический cleanup старых сессий

3. **History sync mechanism:**
   - При потере сессии, replay истории из локального storage
   - Ограничение на context window size

---

## 9. Conclusion

### 9.1 Summary of Findings

Headless коннекторы (Claude CLI и Codex CLI) используют **stateless subprocess model** с **external session management**. Ключевые находки:

✅ **Работает:**
- Session identifiers правильно передаются между вызовами
- Дельта-промпты корректно отправляются в CLI
- JSON parsing надёжен

⚠️ **Ограничения:**
- Полная зависимость от CLI для хранения истории
- Нет проверки валидности сессий
- Нет автоматического recovery

❌ **Критические проблемы:**
- Silent session loss без уведомления
- No fallback при resume failures
- Orphaned sessions в CLI после shutdown

### 9.2 Required Continuous-Session Behavior

**Для полноценного continuous-session поведения нужно:**

1. ✅ **Session identifier persistence** - реализовано
2. ⚠️ **Session validation** - отсутствует
3. ❌ **Session recovery** - не реализовано
4. ❌ **Session cleanup** - не реализовано
5. ⚠️ **History management** - зависит от CLI
6. ✅ **Delta transmission** - реализовано

**Verdict:** Headless коннекторы обеспечивают **базовое continuous-session поведение**, но **не являются fault-tolerant**. При нормальной работе CLI сессии сохраняются, но при ошибках система может потерять контекст без возможности восстановления.

### 9.3 Action Items

**Priority 1 (Критично):**
- [ ] Добавить session validation перед resume
- [ ] Реализовать retry с созданием новой сессии при resume failure
- [ ] Логировать все prime session failures

**Priority 2 (Важно):**
- [ ] Добавить тесты для session loss scenarios
- [ ] Документировать CLI session lifecycle policies
- [ ] Улучшить `is_alive()` для учёта session state

**Priority 3 (Улучшения):**
- [ ] Локальное хранение истории для fallback
- [ ] Session heartbeat проверки
- [ ] Explicit session cleanup в shutdown()

---

**Документ подготовлен:** 21 ноября 2024  
**Версия:** 1.0  
**Статус:** Ready for Review
