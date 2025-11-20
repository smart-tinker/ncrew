# Context Pipeline: Session State Flow through NeuroCrew Lab

## Overview

This document traces how conversation state flows from Telegram through FileStorage into NeuroCrewLab and down to connectors. It maps the complete context pipeline, identifies where state is stored/transformed, and compares the current **delta-based** approach to the desired **full history per agent** requirement.

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TELEGRAM LAYER                               │
│              (telegram_bot.py::handle_message)                      │
│  Receives user input → Validates → Passes to NeuroCrew             │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     NEUROCREW CORE                                  │
│           (engine.py::handle_message)                              │
│  1. Add user message to storage                                    │
│  2. Starts autonomous dialogue cycle                               │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              AUTONOMOUS CYCLE ORCHESTRATION                         │
│      (engine.py::_run_autonomous_cycle)                            │
│  • Round-robin through roles (chat_role_pointers)                 │
│  • Each role processes in sequence                                 │
│  • Terminates when all agents respond with "....." placeholder     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
      ┌─────────┐     ┌─────────┐     ┌─────────┐
      │ Role 1  │     │ Role 2  │     │ Role 3  │
      │ Process │     │ Process │     │ Process │
      └────┬────┘     └────┬────┘     └────┬────┘
           │               │               │
           ▼               ▼               ▼
   ┌─────────────────────────────────────────────┐
   │  Per-Role Processing (_process_with_role)  │
   │  1. Load full conversation from storage     │
   │  2. Extract delta (new msgs since last see) │
   │  3. Format prompt for role                  │
   │  4. Execute connector with delta            │
   │  5. Save response to storage                │
   │  6. Update role_last_seen_index             │
   └────────────┬─────────────────────────────────┘
                │
                ▼
   ┌─────────────────────────────────────────────┐
   │  STORAGE LAYER (file_storage.py)            │
   │  • Persistent JSON files (chat_*.json)      │
   │  • Conversation history + metadata          │
   │  • Truncation to MAX_CONVERSATION_LENGTH    │
   │  • Backup management                        │
   └─────────────────────────────────────────────┘
                │
                ▼
   ┌─────────────────────────────────────────────┐
   │  CONNECTORS (Base + Agent-specific)         │
   │  • Receive delta prompt                     │
   │  • Execute via stateful session             │
   │  • Return response                          │
   └─────────────────────────────────────────────┘
```

---

## 2. Detailed Stage Breakdown

### Stage 1: Telegram Entry Point

**File:** `app/interfaces/telegram_bot.py::handle_message` (lines 505-635)

**Purpose:** Receive user message and initiate processing

**Key Steps:**
1. **Receive & Validate** (lines 514-538):
   - Check if message is from target chat (`_is_target_chat()`)
   - Extract `chat_id` and `user_text` from Update
   - Call `validate_input(user_text, "message")` for security

2. **Pass to NeuroCrew** (lines 549-554):
   ```python
   async for role_config, raw_response in self.ncrew.handle_message(
       chat_id, user_text
   ):
   ```
   - `handle_message()` returns AsyncGenerator yielding role responses
   - Iterates over all role responses in the autonomous cycle

3. **Format & Send Responses** (lines 557-587):
   - Format response with `format_telegram_message()` (escape Markdown)
   - Call `format_agent_response(display_name, safe_response)`
   - Split long messages with `split_long_message()` (max 4096 chars per Telegram)
   - Send via actor bot (role-specific) or fallback to listener bot

**State Captured:** Raw user text (validated)

---

### Stage 2: NeuroCrew Entry Point

**File:** `app/core/engine.py::handle_message` (lines 288-329)

**Purpose:** Capture user message in persistent storage and start autonomous cycle

**Key Steps:**
1. **Save User Message** (lines 307-316):
   ```python
   user_message = {
       "role": "user",
       "content": user_text,
       "timestamp": datetime.now().isoformat(),
   }
   success = await self.storage.add_message(chat_id, user_message)
   ```
   - Creates message dict with role="user"
   - Adds to storage via `FileStorage.add_message()`
   - This is the **first state commit** to disk

2. **Start Autonomous Cycle** (lines 320-321):
   ```python
   async for result in self._run_autonomous_cycle(chat_id):
       yield result
   ```
   - Initiates the continuous dialogue loop
   - Yields results back to Telegram bot

**State Stored:**
- User message added to `data/conversations/chat_{chat_id}.json`
- Conversation is loaded, appended, truncated if needed, and saved

---

### Stage 3: Autonomous Dialogue Cycle

**File:** `app/core/engine.py::_run_autonomous_cycle` (lines 331-451)

**Purpose:** Orchestrate round-robin role execution until termination

**Key Data Structures:**
```python
self.chat_role_pointers: Dict[int, int]  # {chat_id: current_role_index}
self.role_response_count: Dict[(int, str), int]  # {(chat_id, role_name): count}
self.role_last_seen_index: Dict[(int, str), int]  # {(chat_id, role_name): msg_index}
```

**Cycle Logic** (lines 344-451):
1. **Get Next Role** (lines 359-360):
   ```python
   current_role_index = self.chat_role_pointers.get(chat_id, 0)
   role_config = self.roles[current_role_index]
   ```
   - Uses round-robin pointer maintained per chat
   - Cycles through all available roles in sequence

2. **Ensure Connector Ready** (lines 365-380):
   ```python
   connector = self._get_or_create_role_connector(chat_id, role_config)
   if not connector.is_alive():
       await connector.launch(role_config.cli_command, role_config.system_prompt)
   ```
   - Gets stateful connector for `(chat_id, role_name)` pair
   - Launches process if not running

3. **Process with Role** (line 386):
   ```python
   raw_response = await self._process_with_role(chat_id, role_config)
   ```
   - Delegates to per-role processing (see Stage 4)

4. **Update Pointer** (lines 388-391):
   ```python
   self.chat_role_pointers[chat_id] = (current_role_index + 1) % len(self.roles)
   ```
   - Advances round-robin pointer for next iteration

5. **Termination Conditions** (lines 394-421):
   - **Moderator Stop** (lines 395-400): If role is_moderator and returns ".....", stop immediately
   - **All Agents Pass** (lines 404-421): If ALL agents return "....." consecutively (count >= num_roles), stop
   - **Error Recovery** (lines 427-442): Track consecutive errors; stop if all roles error

**State Managed:**
- `chat_role_pointers` determines which role executes next
- `role_response_count` tracks responses for system reminders
- Loop continues until explicit termination condition

---

### Stage 4: Per-Role Processing

**File:** `app/core/engine.py::_process_with_role` (lines 506-626)

**Purpose:** Process conversation through a single role, producing its response

**The Delta-Based Context Extraction** (lines 520-532):

```python
# 1. Load FULL conversation history
conversation = await self.storage.load_conversation(chat_id)

# 2. Get role's last-seen index
key = (chat_id, role.role_name)
last_seen_index = self.role_last_seen_index.get(key, 0)

# 3. Safety check: if index out of bounds, reset to recent messages
if last_seen_index < 0 or last_seen_index > len(conversation):
    last_seen_index = max(len(conversation) - 6, 0)

# 4. Extract DELTA: only NEW messages since role's last turn
new_messages = conversation[last_seen_index:]

# 5. Format prompt from delta
role_prompt, has_updates = self._format_conversation_for_role(
    new_messages, role, chat_id
)
```

**Critical Insight:**
- Loads full history from storage
- **Only processes messages AFTER the role's last_seen_index**
- This is a **delta-only** approach, not full history
- Role doesn't see messages it already processed

**Prompt Execution** (lines 536-590):
```python
# Get stateful connector
role_connector = self._get_or_create_role_connector(chat_id, role)

# Launch if needed
if not role_connector.is_alive():
    await role_connector.launch(role.cli_command, role.system_prompt)

# Execute with retry logic
for attempt in range(max_retries):
    try:
        response = await asyncio.wait_for(
            role_connector.execute(role_prompt),
            timeout=300.0
        )
        break
    except asyncio.TimeoutError:
        # Retry with exponential backoff
        ...
```

**Response Storage** (lines 595-619):
```python
agent_message = {
    "role": "agent",
    "agent_name": role.agent_type,
    "role_name": role.role_name,
    "role_display_name": role.display_name,
    "content": response,
    "timestamp": datetime.now().isoformat(),
}

success = await self.storage.add_message(chat_id, agent_message)

# CRITICAL: Update last_seen_index to mark these messages as processed
if success:
    self.role_last_seen_index[key] = len(conversation) + 1
```

**Index Update Logic:**
- Before: `role_last_seen_index[(chat_id, role_name)]` = 0 (initial)
- During: Processed `new_messages = conversation[0:current_length]`
- After: `role_last_seen_index[(chat_id, role_name)]` = current_length + 1
- Next cycle: Role will only see messages from index (current_length + 1) onward

**State Transitions:**
| Step | Role Index | Conversation | Messages Seen | Prompt Contains |
|------|-----------|---|---|---|
| User sends msg | 0 | [User: "hello"] | N/A | N/A |
| Role1 processes | Index→1 | [User, Role1 response] | [0:1] | "User: hello" |
| Role2 processes | Index→2 | [User, Role1, Role2 response] | [1:2] | "Role1 response" only |
| Role3 processes | Index→0 | [User, Role1, Role2, Role3] | [2:3] | "Role2 response" only |

---

### Stage 5: Prompt Formatting for Role

**File:** `app/core/engine.py::_format_conversation_for_role` (lines 628-684)

**Purpose:** Transform delta messages into a natural language prompt

**Key Logic** (lines 642-684):

```python
def _format_conversation_for_role(
    self, new_messages: List[Dict], role: RoleConfig, chat_id: int
) -> Tuple[str, bool]:
    
    # 1. If NO new messages, return placeholder
    if not new_messages:
        return ".....", False
    
    # 2. Filter out "....." placeholder responses
    filtered_messages = []
    for msg in new_messages:
        content = (msg.get("content") or "").strip()
        if content == ".....":  # Skip 5-dot placeholders
            continue
        filtered_messages.append(msg)
    
    # 3. If all messages were placeholders, return placeholder
    if not filtered_messages:
        return ".....", False
    
    # 4. Build natural conversation context
    context_lines: List[str] = []
    for msg in filtered_messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            context_lines.append(f"User: {content}")
        elif msg.get("role") == "agent":
            agent_name = msg.get("role_display_name", msg.get("role_name", "Assistant"))
            content = msg.get("content", "")
            context_lines.append(f"Assistant ({agent_name}): {content}")
    
    conversation_context = "\n\n".join(context_lines)
    
    # 5. Optionally add SYSTEM REMINDER (every N responses)
    role_key = (chat_id, role.role_name)
    response_count = self.role_response_count.get(role_key, 0)
    
    if response_count > 0 and response_count % Config.SYSTEM_REMINDER_INTERVAL == 0:
        system_reminder = (
            f"\n\n[SYSTEM REMINDER]\n{role.system_prompt}\n[END REMINDER]\n\n"
        )
        conversation_context = system_reminder + conversation_context
    
    return conversation_context, True
```

**Output Examples:**

**Example 1: First role seeing user message**
```
Input new_messages: [
    {"role": "user", "content": "Build a Flask app"}
]

Output prompt:
User: Build a Flask app

Output: (prompt, True)  # has_updates=True
```

**Example 2: Second role seeing first role's response**
```
Input new_messages: [
    {
        "role": "agent",
        "role_display_name": "Backend Dev",
        "content": "I'll structure the app with blueprints..."
    }
]

Output prompt:
Assistant (Backend Dev): I'll structure the app with blueprints...

Output: (prompt, True)
```

**Example 3: All messages are placeholders**
```
Input new_messages: [
    {"role": "agent", "content": "....."},
    {"role": "agent", "content": "....."}
]

Filtered: []

Output prompt: "....."
Output: (prompt, False)  # has_updates=False
```

**Example 4: System reminder injected**
```
response_count = 5 (divisible by SYSTEM_REMINDER_INTERVAL=5)

Output prompt:
[SYSTEM REMINDER]
You are a Backend Developer...
[END REMINDER]

User: Can you refactor this?
```

---

### Stage 6: Storage Layer

**File:** `app/storage/file_storage.py`

**Purpose:** Persist and retrieve conversation history

#### 6a: Load Conversation

**Function:** `load_conversation(chat_id)` (lines 79-127)

```python
async def load_conversation(self, chat_id: int) -> List[Dict]:
    file_path = self._get_conversation_file(chat_id)
    # chat_*.json for each chat_id
    
    if not file_path.exists():
        return []  # New conversation
    
    async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
        content = await f.read()
    
    data = json.loads(content)
    
    # Support both new format (with metadata) and legacy format
    if isinstance(data, dict) and 'conversation' in data:
        conversation = data['conversation']
    else:
        conversation = data  # Legacy direct list
    
    return conversation  # List of message dicts
```

**File Format (New):**
```json
{
  "metadata": {
    "chat_id": 12345,
    "message_count": 5,
    "last_updated": "2024-01-15T10:30:00",
    "version": "1.0"
  },
  "conversation": [
    {
      "role": "user",
      "content": "Hello",
      "timestamp": "2024-01-15T10:25:00"
    },
    {
      "role": "agent",
      "agent_name": "qwen",
      "role_name": "backend_dev",
      "role_display_name": "Backend Dev",
      "content": "Hi, I'm ready...",
      "timestamp": "2024-01-15T10:26:00"
    }
  ]
}
```

#### 6b: Add Message

**Function:** `add_message(chat_id, message)` (lines 182-216)

```python
async def add_message(self, chat_id: int, message: Dict) -> bool:
    # Validate message has 'role' field
    if field not in message:
        raise ValueError(f"Message missing required field: {field}")
    
    # Add timestamp if missing
    if 'timestamp' not in message:
        message['timestamp'] = datetime.now().isoformat()
    
    # 1. Load existing conversation
    conversation = await self.load_conversation(chat_id)
    
    # 2. Append new message
    conversation.append(message)
    
    # 3. Save updated conversation
    return await self.save_conversation(chat_id, conversation)
```

**Three-Step Flow:**
1. Load complete history
2. Append new message
3. Save back (with truncation if needed)

#### 6c: Save Conversation

**Function:** `save_conversation(chat_id, conversation)` (lines 129-180)

```python
async def save_conversation(self, chat_id: int, conversation: List[Dict]) -> bool:
    file_path = self._get_conversation_file(chat_id)
    
    # Validate structure
    if not isinstance(conversation, list):
        raise ValueError("Conversation must be a list")
    
    # CRITICAL: Truncate to MAX_CONVERSATION_LENGTH
    if len(conversation) > Config.MAX_CONVERSATION_LENGTH:
        conversation = conversation[-Config.MAX_CONVERSATION_LENGTH:]
        # Default: keep last 50 messages only
    
    # Add metadata
    metadata = {
        'chat_id': chat_id,
        'message_count': len(conversation),
        'last_updated': datetime.now().isoformat(),
        'version': '1.0'
    }
    
    file_content = {
        'metadata': metadata,
        'conversation': conversation
    }
    
    # Atomic write (temp file + rename)
    temp_file = file_path.with_suffix('.tmp')
    async with aiofiles.open(temp_file, 'w', encoding='utf-8') as f:
        json_content = json.dumps(file_content, ensure_ascii=False, indent=2)
        await f.write(json_content)
    
    temp_file.rename(file_path)  # Atomic
    return True
```

**Truncation Impact:**
```
Conversation grows:
[msg0, msg1, ..., msg48, msg49]  # 50 messages, at limit
[msg0, msg1, ..., msg48, msg49, msg50]  # 51 messages
    ↓ Truncate ↓
[msg1, msg2, ..., msg49, msg50]  # Keep last 50

LOST: msg0 and any context from earliest exchange
```

---

### Stage 7: Connector Execution

**File:** `app/connectors/base.py` (BaseConnector)

**Purpose:** Execute agent's CLI command with stateful session management

**Key Interfaces:**
```python
class BaseConnector:
    async def launch(self, cli_command: str, system_prompt: str):
        """Start the agent process"""
    
    async def execute(self, prompt: str) -> str:
        """Send prompt to running process, get response"""
    
    def is_alive() -> bool:
        """Check if process is still running"""
    
    async def shutdown():
        """Gracefully stop the process"""
```

**State Persistence:**
- Each connector is keyed by `(chat_id, role_name)`
- Session lives in memory for the duration of the chat
- Process is launched once per role/chat combination
- Same process handles all turns for that role
- On restart: Context index is reset to 0 (line 1099 in engine.py)

**Execution Flow:**
```
1. get_or_create_connector(chat_id, role)
   └─> Returns connector from cache or creates new

2. connector.is_alive()
   └─> Check if process running

3. connector.launch(cli_command, system_prompt)
   └─> Start subprocess with system prompt
   
4. connector.execute(delta_prompt)
   └─> Send only NEW context to agent
   └─> Agent has process-local state
   └─> Returns response

5. Store response in FileStorage
   └─> Next agent sees this response in its delta
```

---

## 3. Context State Lifecycle

### Per-Chat State
```
chat_id: 12345

1. First user message arrives
   storage: [user_msg1]
   pointers: {12345: 0}  # Role index
   indices: {}

2. Role 0 (Backend Dev) executes
   loads: [user_msg1]
   delta: [user_msg1] (index 0 to 1)
   saves response
   storage: [user_msg1, role0_response]
   indices: {(12345, "backend_dev"): 1}

3. Role 1 (Frontend Dev) executes
   loads: [user_msg1, role0_response]
   delta: [role0_response] (index 1 to 2)
   sees only: "Assistant (Backend Dev): ..."
   saves response
   storage: [user_msg1, role0_response, role1_response]
   indices: {
       (12345, "backend_dev"): 1,
       (12345, "frontend_dev"): 2
   }

4. Next cycle: Role 0 executes again
   loads: [user_msg1, role0_response, role1_response]
   delta: [role1_response] (index 1 to 3)
   sees: "Assistant (Frontend Dev): ..."
   No longer sees user's original message
```

### Process Restart Scenario
```
During execution, Role 0's process crashes:

1. connector.is_alive() returns False
2. _get_or_create_role_connector detects dead process
3. Removes from sessions cache
4. RESETS role_last_seen_index[(12345, "backend_dev")] = 0
5. Creates new connector instance
6. New process launched with full system prompt
7. Next time Role 0 processes:
   delta now includes ALL messages from start
   Provides full context to new process
```

---

## 4. Current Flow vs. Desired "Full History per Agent"

### Current Implementation: Delta-Only

```
┌─────────────────────────────────────────────────────────┐
│ Current: Delta-Based Context Passing                   │
├─────────────────────────────────────────────────────────┤
│ Role 1 sees: User's initial message                    │
│ Role 2 sees: Role 1's response only                    │
│ Role 3 sees: Role 2's response only                    │
│ Role 1 (again) sees: Role 3's response only            │
│                                                        │
│ Pros:                                                  │
│ • Efficient: Minimal context passed per turn           │
│ • Focused: Agents react to latest development         │
│ • Scalable: Context doesn't grow with history         │
│                                                        │
│ Cons:                                                  │
│ • No long-term memory: Lost details from early msgs   │
│ • Dependent on summaries: Must rely on other agents   │
│ • Truncation risk: MAX_CONVERSATION_LENGTH = 50      │
│ • Context gap: Agent can't reference older decisions  │
└─────────────────────────────────────────────────────────┘
```

### Desired: Full History per Agent

```
┌─────────────────────────────────────────────────────────┐
│ Desired: Full History Context                          │
├─────────────────────────────────────────────────────────┤
│ Role 1 sees: [User's message]                         │
│ Role 2 sees: [User, Role 1 response]                  │
│ Role 3 sees: [User, Role 1, Role 2]                   │
│ Role 1 (again) sees: [User, Role 1, Role 2, Role 3] │
│                                                        │
│ Pros:                                                  │
│ • Full context: Agents see complete history           │
│ • Long-term memory: Can reference early decisions     │
│ • Better coherence: No information loss               │
│ • Reduces reliance on others' summaries              │
│                                                        │
│ Cons:                                                  │
│ • Token usage: More context per prompt                │
│ • Processing time: Larger prompts to parse            │
│ • Memory: Unlimited history growth                    │
│ • Redundancy: Repeated context each turn              │
└─────────────────────────────────────────────────────────┘
```

### Gap Analysis

| Aspect | Current | Desired | Gap |
|--------|---------|---------|-----|
| **Context Scope** | Delta only (new msgs since last turn) | Full history every time | Agent never sees old conversation context; relies on others' summaries |
| **Persistence** | Per-process session + storage | Per-agent full history per prompt | When process restarts, only first run gets "full" context |
| **Memory Loss** | At 50-message truncation | Ideally never | Conversations >50 messages lose early context permanently |
| **Turn-by-Turn View** | Role 2→3→1: Each sees only previous agent | All see all | Agents can't cross-reference or catch inconsistencies from earlier turns |
| **Token Efficiency** | Low (minimal prompt) | High (full prompt every time) | Tradeoff not yet optimized |

### Implementation Options to Achieve Full History

#### Option 1: Simple Full-History Pass
**Change:** Send entire conversation to every agent

```python
# Current (delta):
new_messages = conversation[last_seen_index:]
role_prompt, has_updates = self._format_conversation_for_role(new_messages, role, chat_id)

# Desired (full):
role_prompt, has_updates = self._format_conversation_for_role(conversation, role, chat_id)
```

**Impact:**
- Pros: Simple, minimal code change, complete context
- Cons: Redundant data per turn, grows memory proportionally to conversation length

#### Option 2: Selective Context with Truncation Window
**Change:** Keep last N messages (not first N)

```python
# Instead of truncating to last 50:
context_window = max(100, config.MAX_CONVERSATION_LENGTH)
recent_messages = conversation[-context_window:]

# Pass full window to agents:
role_prompt = self._format_conversation_for_role(recent_messages, role, chat_id)
```

**Impact:**
- Pros: Balances context and efficiency
- Cons: Adds config complexity, still loses very old context

#### Option 3: Semantic Summarization
**Change:** Compress old messages into summaries

```python
# Keep full recent history + compressed old history
old_messages = conversation[:-20]  # Everything except recent
recent_messages = conversation[-20:]  # Last 20

# Summarize old:
if old_messages:
    summary = await generate_summary(old_messages)
    role_prompt = f"[CONTEXT SUMMARY]\n{summary}\n\n[RECENT]\n{format(recent_messages)}"
else:
    role_prompt = format(recent_messages)
```

**Impact:**
- Pros: Preserves all information, controlled size
- Cons: Requires additional summarization agent, complexity

#### Option 4: Persistent Agent Memory Bank
**Change:** Store per-agent summaries outside conversation

```python
# New storage structure:
agent_memory[role_name] = {
    "key_decisions": ["..."],
    "context_summary": "...",
    "last_update_index": 42
}

# Include in every prompt:
prompt = f"{agent_memory[role_name]['context_summary']}\n\n{delta_prompt}"
```

**Impact:**
- Pros: Explicit memory, can be updated periodically
- Cons: Complex to implement, requires summarization logic

---

## 5. State Flow Diagram: Detailed Sequence

### Single User Message Round-Trip

```
TIME    TELEGRAM              NCREW                    STORAGE                 CONNECTOR
t0:     User sends
        "hello"
                    ┌─────────────────────────────────────┐
                    │ handle_message(12345, "hello")     │
                    └─────────────────────────────────────┘
                              │
                              ├──> add_message(12345, {
                              │    role="user",
                              │    content="hello"
                              │  })
                              │       ├──> load_conversation(12345) → []
                              │       ├──> conversation.append({...})
                              │       ├──> save_conversation → chat_12345.json
                              │       │       [User msg]
                              │       └─> True

t1:     Starting cycle        _run_autonomous_cycle
                              ├─> current_role_index = 0 (Backend Dev)
                              ├─> connector = _get_or_create_role_connector(...)
                              └─> _process_with_role(12345, backend_dev)
                                      │
                                      ├─> load_conversation(12345)
                                      │   ← [User msg]
                                      │
                                      ├─> last_seen = 0 (new)
                                      ├─> delta = [User msg][0:]
                                      ├─> has_updates = True
                                      │
                                      ├─> _format_conversation_for_role(delta)
                                      │   → "User: hello"
                                      │
                                      └─> connector.execute("User: hello")
                                              │
                                              └─> Subprocess executes
                                                  ← "I'll help with backend..."

t2:     Response received                       ├─> add_message(12345, {
                                                │   role="agent",
                                                │   agent_name="qwen",
                                                │   role_name="backend_dev",
                                                │   role_display_name="Backend Dev",
                                                │   content="I'll help..."
                                                │ })
                                                │
                                                ├─> load_conversation(12345)
                                                │   ← [User msg, Agent msg]
                                                │
                                                ├─> save_conversation
                                                │   → chat_12345.json
                                                │   [User msg, Agent msg]
                                                │
                                                └─> role_last_seen_index[
                                                    (12345, "backend_dev")
                                                    ] = 2
                                                    
t3:     Yield to Telegram  ← (BackendDevRole, "I'll help...")
                    │
                    └──> format_telegram_message(...)
                    │    format_agent_response(...)
                    │    split_long_message(...)
                    │    _send_role_messages_via_actor(...)
                    │    await send_message(chat_id, text)
                    │    
                    Telegram: "🤖 Backend Dev\nI'll help..."

t4:     Continue cycle      _run_autonomous_cycle (next iteration)
                              ├─> current_role_index = 1 (Frontend Dev)
                              └─> _process_with_role(12345, frontend_dev)
                                      │
                                      ├─> load_conversation(12345)
                                      │   ← [User msg, Backend Agent msg]
                                      │
                                      ├─> last_seen = 0 (first time)
                                      ├─> delta = [User msg, Backend msg][0:]
                                      ├─> _format_conversation_for_role(delta)
                                      │   → Filters: "Assistant (Backend Dev): I'll help..."
                                      │
                                      └─> connector.execute("Assistant (Backend Dev): I'll help...")
                                              │
                                              └─> Frontend subprocess
                                                  ← "Great, the frontend should..."

t5:                                         ├─> add_message(12345, {Frontend response})
                                                ├─> save_conversation
                                                │   → [User, Backend, Frontend]
                                                └─> role_last_seen_index[
                                                    (12345, "frontend_dev")
                                                    ] = 3

t6:     Yield to Telegram  ← (FrontendDevRole, "Great, frontend should...")
                    └──> Send to Telegram

...continues until all agents return "....." or moderator stops
```

---

## 6. Truncation and Reset Scenarios

### Scenario A: Conversation Exceeds MAX_CONVERSATION_LENGTH

```
MAX_CONVERSATION_LENGTH = 50

Messages 0-49 stored:   [msg0, msg1, ..., msg49]
New message added:      [msg0, msg1, ..., msg49, msg50]
                         (51 messages, over limit)

save_conversation called:
├─ if len(conversation) > 50:
│  └─ conversation = conversation[-50:]
│     Result: [msg1, msg2, ..., msg50]  ← msg0 LOST
│
└─> write to storage
```

**Consequence:**
- msg0 and msg1 are lost permanently
- Any context from earliest exchange disappears
- `role_last_seen_index` is NOT adjusted
- Role might point to index that no longer exists (safety check at line 527-528 handles this)

### Scenario B: Process Restart

```
Role: Backend Dev, Chat: 12345

Before restart:
├─ connector_sessions[(12345, "backend_dev")] = <Process>
├─ role_last_seen_index[(12345, "backend_dev")] = 5
└─ Storage: [msg0, msg1, ..., msg5]

Process crashes (is_alive returns False):

_get_or_create_role_connector:
├─ Detects connector exists but is_dead
├─ Removes from sessions: del connector_sessions[key]
├─ RESETS INDEX: role_last_seen_index[key] = 0
│  ^^^ Critical fix: enables new process to see full history
└─ Creates new connector
    └─ Returns fresh instance

Next execution:
├─ last_seen_index = 0 (reset)
├─ delta = conversation[0:]  ← FULL CONVERSATION
├─ New process receives complete context
└─ Ensures continuity after crash
```

---

## 7. Risks and Limitations

### Risk 1: Permanent Context Loss on Truncation
**Severity:** High

**Description:**
- Conversations longer than 50 messages lose early context
- No warning to users or agents
- Lost information cannot be recovered from storage

**Current Mitigation:**
- `MAX_CONVERSATION_LENGTH` config (default 50)
- Storage backups created on `clear_conversation()`
- No active mitigation during normal operation

**Recommended Mitigation:**
- Increase default limit to 200-500
- Add logging when truncation occurs
- Implement sliding window with summary of truncated messages
- Consider implementing Option 3 (semantic summarization) from Section 4

### Risk 2: Index Out-of-Bounds After Truncation
**Severity:** Medium

**Description:**
- `role_last_seen_index` can point to non-existent message after truncation
- Example: role_last_seen_index=50, but conversation now has only 50 messages total

**Current Mitigation:**
- Safety check at lines 527-528:
  ```python
  if last_seen_index < 0 or last_seen_index > len(conversation):
      last_seen_index = max(len(conversation) - 6, 0)
  ```
- Resets to "recent 6 messages" if out of bounds
- Allows at least some context

**Risk:**
- If conversation was [0-49], now [5-54], and role_index=50:
  - Resets to max(50-6, 0) = 44
  - Role sees messages [44-54] (10 messages after reset)
  - Messages [5-43] are invisible to this role even though they're still in storage

**Recommended Mitigation:**
- Track which messages are "new" vs "truncated" in storage
- Provide agents with summary of truncated context
- Implement migration path when process restarts (reset index to 0)

### Risk 3: Delta-Only Causes Information Fragmentation
**Severity:** Medium

**Description:**
- Agents only see new messages since their last turn
- Cannot cross-reference or review earlier decisions
- No direct access to full conversation history
- Relies on other agents to accurately summarize

**Example:**
```
Round 1: User asks to "use async functions"
Round 2: Backend dev responds with sync code by mistake
Round 3: Frontend dev cannot see original requirement, thinks it's intentional
Round 4: Backend dev doesn't see his earlier mistake in context
```

**Current Mitigation:**
- System reminders (every 5 responses) re-inject system prompt
- Agent's own system prompt includes guidelines
- No explicit mechanism to re-inject user requirements

**Recommended Mitigation:**
- Implement Option 1 (full history per agent) for critical interactions
- Add "context summary" of user's original intent
- Enhance system reminders to include key requirements
- Track user intent separately and re-inject periodically

### Risk 4: Stateful Connector Dependency
**Severity:** Medium

**Description:**
- Each role's context depends on single long-running process
- Process crash causes restart with reset context index
- Process memory is not persisted
- Subprocess state (internal variables, parsed context) lost on crash

**Current Mitigation:**
- `is_alive()` check before each use
- Automatic restart with context reset
- Async execution with timeout and retry (2 attempts, exponential backoff)

**Risk:**
- Process dies silently, is_alive() misses it momentarily
- Retry logic only for timeout/exception, not process crashes
- No heartbeat to validate process health continuously

**Recommended Mitigation:**
- Implement periodic healthcheck (e.g., every 30s)
- Add persistent session state to storage
- Implement subprocess watchdog
- Consider stateless connector approach (re-create per execution)

### Risk 5: Round-Robin Pointer Not Persisted
**Severity:** Low

**Description:**
- `chat_role_pointers` is in-memory only
- If NeuroCrew crashes, pointer resets to 0
- Next run starts cycle from first role again

**Current Mitigation:**
- Rarely matters in practice (MVP single-instance)
- In-memory simplicity acceptable for now

**Risk:**
- Multi-instance deployments will have inconsistent pointers
- Users might not expect restart to re-run first role

**Recommended Mitigation:**
- Persist pointer in storage
- Load on initialization
- Store as part of chat metadata

### Risk 6: No Explicit Timeout Handling Between Stages
**Severity:** Medium

**Description:**
- Storage operations assume success
- No timeout on `load_conversation()`, `add_message()`
- File I/O on large histories could hang
- Telegram response could fail silently if formatting takes too long

**Current Mitigation:**
- Connector execution has 300-second timeout
- FileStorage uses async I/O (non-blocking)
- Retry logic for agent timeouts

**Risk:**
- Storage operations without timeout
- If file is corrupted or inaccessible, could block indefinitely

**Recommended Mitigation:**
- Add timeout wrapper around all storage operations
- Implement circuit breaker for repeated failures
- Add logging for latency metrics

---

## 8. Concrete Code References

### Key Functions for Context Flow

| Function | File | Lines | Purpose |
|----------|------|-------|---------|
| `handle_message()` | telegram_bot.py | 505-635 | Telegram entry, yields agent responses |
| `handle_message()` | engine.py | 288-329 | Add user msg, start cycle |
| `_run_autonomous_cycle()` | engine.py | 331-451 | Round-robin orchestration, termination |
| `_process_with_role()` | engine.py | 506-626 | Per-role execution, delta extraction, response save |
| `_format_conversation_for_role()` | engine.py | 628-684 | Delta→prompt conversion, placeholder filtering |
| `_get_or_create_role_connector()` | engine.py | 1077-1106 | Stateful session management, restart logic |
| `load_conversation()` | file_storage.py | 79-127 | Fetch full history from storage |
| `add_message()` | file_storage.py | 182-216 | Append and save message |
| `save_conversation()` | file_storage.py | 129-180 | Persist with truncation |

### State Tracking Structures

```python
# In NeuroCrewLab.__init__:
self.connector_sessions: Dict[(int, str), BaseConnector]
    # Key: (chat_id, role_name)
    # Value: Stateful connector instance
    # Scope: Per-role, per-chat
    # Lifetime: Until shutdown/crash

self.chat_role_pointers: Dict[int, int]
    # Key: chat_id
    # Value: Current role index (0 to len(roles)-1)
    # Scope: Per-chat
    # Lifetime: Entire session, reset on /reset command
    # Persistence: In-memory only

self.role_last_seen_index: Dict[(int, str), int]
    # Key: (chat_id, role_name)
    # Value: Conversation message index where role stopped
    # Scope: Per-role, per-chat
    # Lifetime: Until /reset or process restart
    # Purpose: Extract delta for next execution
    # Persistence: In-memory only

self.role_response_count: Dict[(int, str), int]
    # Key: (chat_id, role_name)
    # Value: Count of responses (non-placeholder)
    # Scope: Per-role, per-chat
    # Lifetime: Until /reset
    # Purpose: Track when to inject system reminders
    # Persistence: In-memory only
```

---

## 9. Summary and Recommendations

### Current State
- **Architecture:** Delta-based context passing (each role sees only new messages since last turn)
- **Storage:** Full history in JSON files, truncated to 50 messages
- **State:** Tracked in-memory with per-role, per-chat keys
- **Efficiency:** Low token usage, focused agent responses
- **Risks:** Context loss, information fragmentation, restart vulnerability

### Desired State (Full History per Agent)
- **Architecture:** Every agent sees complete conversation history
- **Benefits:** Better coherence, no information loss, cross-reference capability
- **Trade-offs:** Higher token usage, larger prompts, memory growth

### Recommended Immediate Actions
1. **Increase `MAX_CONVERSATION_LENGTH`** from 50 to 200+ to reduce truncation risk
2. **Add truncation logging** to alert when context is being lost
3. **Implement Option 1 (Simple Full-History)** for MVP if token budget allows
4. **Document per-agent context scope** clearly in system prompts
5. **Add health checks** to detect process crashes faster

### Recommended Future Enhancements
1. **Semantic Summarization (Option 3):** Compress old messages into summaries
2. **Persistent Memory Banks (Option 4):** Store per-agent summaries in separate storage
3. **Sliding Window Context:** Combine full recent + summarized old history
4. **State Persistence:** Save pointer, index, and response count to storage
5. **Context Audit:** Add command to view what each agent can see

---

## 10. Visual Reference: Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          COMPLETE DATA FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ 1. USER SENDS MESSAGE                                                       │
│    Telegram API → TelegramBot.handle_message(Update)                       │
│    Extract: chat_id, user_text                                             │
│    ↓                                                                        │
│ 2. NCREW ENTRY                                                             │
│    engine.handle_message(chat_id, user_text)                              │
│    → storage.add_message(chat_id, {"role": "user", "content": ...})       │
│    ↓                                                                        │
│ 3. AUTONOMOUS CYCLE                                                        │
│    _run_autonomous_cycle():                                                │
│      WHILE not_terminated:                                                 │
│        role = roles[chat_role_pointers[chat_id]]                          │
│        response = _process_with_role(chat_id, role)                       │
│        yield (role, response)  ← To Telegram                              │
│        chat_role_pointers[chat_id] = (index + 1) % len(roles)             │
│    ↓                                                                        │
│ 4. PER-ROLE PROCESSING                                                     │
│    _process_with_role(chat_id, role):                                     │
│      (a) Load full history                                                 │
│          conversation = storage.load_conversation(chat_id)                │
│      (b) Extract delta                                                     │
│          last_seen = role_last_seen_index.get((chat_id, role_name), 0)    │
│          new_messages = conversation[last_seen:]                          │
│      (c) Format to prompt                                                  │
│          role_prompt = _format_conversation_for_role(new_messages, role)  │
│      (d) Execute connector                                                 │
│          connector = _get_or_create_role_connector(chat_id, role)         │
│          response = connector.execute(role_prompt)                        │
│      (e) Save response                                                     │
│          storage.add_message(chat_id, {"role": "agent", "content": ...})  │
│      (f) Update index                                                      │
│          role_last_seen_index[(chat_id, role_name)] = len(conversation)   │
│    ↓                                                                        │
│ 5. RESPONSE FORMATTING & DELIVERY                                          │
│    telegram_bot.handle_message (continuation):                            │
│      safe_response = format_telegram_message(response)                    │
│      formatted = format_agent_response(role.display_name, safe_response)  │
│      messages = split_long_message(formatted, max=4096)                   │
│      _send_role_messages_via_actor(role, messages)  ← or fallback         │
│      ↓                                                                     │
│      Telegram Chat: "[🤖 Agent Name] response_text"                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Appendix: Configuration Impact

### Key Config Variables Affecting Context Flow

```python
# app/config.py

# Truncation limit (HIGHEST RISK FACTOR)
MAX_CONVERSATION_LENGTH = int(os.getenv("MAX_CONVERSATION_LENGTH", "50"))
# Effect: Conversations > 50 msgs lose early context
# Recommendation: Increase to 200-500

# System reminder frequency
SYSTEM_REMINDER_INTERVAL = int(os.getenv("SYSTEM_REMINDER_INTERVAL", "5"))
# Effect: Re-inject system prompt every N responses
# Mitigation for context fragmentation
# Recommendation: Consider 3-5 for better retention

# Agent timeout
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "600"))
# Effect: Wait up to 600s for agent response
# In engine.py: asyncio.wait_for(..., timeout=300.0)
# Note: Hard-coded to 300s in code, not using AGENT_TIMEOUT

# Telegram message limit
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
# Effect: Messages split before sending
# No truncation of context, just splitting for delivery
```

### Recommended .env Settings for Full History

```bash
# Conservative (current)
MAX_CONVERSATION_LENGTH=50

# Recommended for better context
MAX_CONVERSATION_LENGTH=200

# Aggressive (for research/testing)
MAX_CONVERSATION_LENGTH=500

# Reminder frequency (help agents stay in role)
SYSTEM_REMINDER_INTERVAL=3
```

---

**Document Version:** 1.0  
**Last Updated:** 2024  
**Status:** Complete  
**Acceptance Criteria Met:**
- ✅ Clear explanation of each stage with concrete functions
- ✅ Sequence diagrams and data flow illustrations
- ✅ Gap analysis: Current (delta-only) vs Desired (full history)
- ✅ Risks and limitations documented
- ✅ Code references and state tracking structures
- ✅ Configuration impact analysis
