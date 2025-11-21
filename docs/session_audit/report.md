# Session Audit Report
**Date:** November 21, 2024  
**Status:** Comprehensive Analysis Complete  
**Scope:** Multi-turn context transfer across all NeuroCrewLab agents  
**Version:** 1.0

---

## Executive Summary

This report synthesizes findings from the pipeline review and connector analyses to evaluate session continuity across all five NeuroCrewLab agents (OpenCode, Qwen, Gemini, Claude, Codex). The audit reveals a **fundamental architectural gap**: the current implementation uses **delta-based context passing** instead of the required **full-history session handling** per user requirements.

**Key Finding:** While all connectors maintain session state correctly, the NeuroCrewLab engine only passes new messages (deltas) to each agent, preventing agents from accessing complete conversation history needed for coherent multi-turn dialogues.

**Critical Impact:** Requirements US-03 (session reuse) and US-01 (team discussion) are partially implemented but fail to deliver full context awareness, limiting the system's ability to maintain coherent long-term conversations.

---

## User Requirements Mapping

| Requirement | Current Implementation | Gap Analysis | Evidence |
|-------------|----------------------|--------------|----------|
| **US-01**: Team discussion in chat | ✅ Messages stored in FileStorage<br>✅ Multiple agents respond in sequence<br>✅ Telegram routing works | ❌ Agents only see delta, not full history<br>❌ Cannot reference earlier decisions | [context_pipeline.md#Stage4](context_pipeline.md#stage-4-per-role-processing) |
| **US-02**: Role configuration via YAML | ✅ Roles loaded from `roles/agents.yaml`<br>✅ Token/command validation<br>✅ `/agents` command shows sequence | ✅ Fully implemented | [USER_STORIES.md](../USER_STORIES.md) |
| **US-03**: CLI session reuse | ✅ Connectors maintain session IDs<br>✅ Stateful processes for ACP<br>✅ Session persistence for CLI | ❌ Engine resets context to delta only<br>❌ No full history passing | [headless_connectors.md](headless_connectors.md) |
| **US-04**: Headless CLI auth from env | ✅ Claude/Codex use system auth<br>✅ No API keys in project<br>✅ CLI error handling | ✅ Fully implemented | [USER_STORIES.md](../USER_STORIES.md) |
| **US-05**: Moderator reset | ✅ `/reset` clears conversation<br>✅ Connectors shutdown properly<br>✅ User confirmation | ✅ Fully implemented | [test_ncrew_core.py](../../tests/test_ncrew_core.py) |
| **US-06**: Status commands | ✅ `/status` shows agent availability<br>✅ `/metrics` provides counters<br>✅ `/next` advances queue | ✅ Fully implemented | [test_start_command.py](../../tests/test_start_command.py) |

---

## Current Architecture Analysis

### 1. Context Flow Pipeline

The system follows a six-stage pipeline ([context_pipeline.md](context_pipeline.md)):

```
Telegram → NeuroCrewLab → Storage → Delta Extraction → Connector → Agent
```

**Critical Issue:** Stage 4 (Delta Extraction) only passes messages since the agent's last turn:

```python
# Extract DELTA: only NEW messages since role's last turn
new_messages = conversation[last_seen_index:]
```

This means:
- Role 1 sees: User's initial message
- Role 2 sees: Only Role 1's response  
- Role 3 sees: Only Role 2's response
- Role 1 (again) sees: Only Role 3's response

**Result:** No agent has complete conversation context.

### 2. Session State Management

#### ACP Connectors (OpenCode, Qwen, Gemini)
- **Status:** ✅ Session management working correctly
- **Protocol:** Long-lived subprocess with bidirectional stdin/stdout
- **Session ID:** Generated and maintained by CLI agent
- **Context:** Server-side (CLI agent) maintains full history
- **Evidence:** [ACP connectors audit](acp_connectors.md)

#### Headless Connectors (Claude, Codex)  
- **Status:** ✅ Session management working correctly
- **Protocol:** Stateless subprocess with session identifiers
- **Session ID:** Managed via `--session-id`/`--resume` flags
- **Context:** Client-side (CLI tool) maintains full history
- **Evidence:** [Headless connectors audit](headless_connectors.md)

### 3. Storage Layer Behavior

FileStorage ([context_pipeline.md#Stage6](context_pipeline.md#stage-6-storage-layer)):
- ✅ Correctly persists complete conversation history
- ✅ Atomic writes with backup management
- ⚠️ **Truncation Risk:** `MAX_CONVERSATION_LENGTH = 50` messages
- ⚠️ **Early Context Loss:** Messages beyond limit are permanently lost

---

## Session Continuation Checklist

| Agent | Session Continuity | Full History Context | Implementation Status | Evidence |
|-------|-------------------|----------------------|---------------------|----------|
| **OpenCode** | ✅ **PASS** | ❌ **FAIL** | Session ID maintained, but only delta context passed | [test_opencode_acp.py](../../tests/test_opencode_acp.py) |
| **Qwen** | ✅ **PASS** | ❌ **FAIL** | ACP protocol working, delta-only context | [test_qwen_acp.py](../../tests/test_qwen_acp.py) |
| **Gemini** | ✅ **PASS** | ❌ **FAIL** | Session persistence correct, delta-only context | [test_gemini_acp.py](../../tests/test_gemini_acp.py) |
| **Claude** | ✅ **PASS** | ❌ **FAIL** | Session ID resume working, delta-only context | [test_claude_cli_connector.py](../../tests/test_claude_cli_connector.py) |
| **Codex** | ✅ **PASS** | ❌ **FAIL** | Thread ID persistence working, delta-only context | [test_codex_cli_connector.py](../../tests/test_codex_cli_connector.py) |

**Summary:** All agents pass session continuity but fail full-history context transfer.

---

## Detailed Findings by Connector

### OpenCode ACP Connector
**File:** `app/connectors/opencode_acp_connector.py`  
**Session Management:** ✅ Correct  
- Long-lived subprocess process
- Session ID generated by CLI agent
- Bidirectional JSON-RPC 2.0 communication
- Auto-grants permissions on first use

**Context Handling:** ❌ Delta-only  
- Receives only new messages from engine
- Full history maintained on CLI side
- No context loss within session

**Evidence:** [ACP connectors audit](acp_connectors.md#31-opencode-acp-connector)

### Qwen ACP Connector  
**File:** `app/connectors/qwen_acp_connector.py`  
**Session Management:** ✅ Correct  
- Identical architecture to OpenCode
- Experimental ACP 0.1.4 protocol
- OAuth capability detection (unused)

**Context Handling:** ❌ Delta-only  
- Same delta limitation as other ACP connectors
- Server-side context management

**Evidence:** [ACP connectors audit](acp_connectors.md#32-qwen-acp-connector)

### Gemini ACP Connector
**File:** `app/connectors/gemini_acp_connector.py`  
**Session Management:** ✅ Correct  
- Experimental ACP protocol
- API key capability detection (unused)
- Fixed copy-paste error in stderr handling

**Context Handling:** ❌ Delta-only  
- Consistent with ACP architecture

**Evidence:** [ACP connectors audit](acp_connectors.md#33-gemini-acp-connector)

### Claude CLI Connector
**File:** `app/connectors/claude_cli_connector.py`  
**Session Management:** ✅ Correct  
- Stateless subprocess model
- Session ID generated locally
- `--session-id` for creation, `--resume` for continuation
- Session priming with system prompt

**Context Handling:** ❌ Delta-only  
- Each call spawns new process
- History maintained by Claude CLI
- Process death between calls

**Evidence:** [Headless connectors audit](headless_connectors.md#1-claude-cli-connector)

### Codex CLI Connector
**File:** `app/connectors/codex_cli_connector.py`  
**Session Management:** ✅ Correct  
- Thread ID based persistence
- `Init` vs `Resume` command modes
- UUID generation for session tracking

**Context Handling:** ❌ Delta-only  
- Similar to Claude architecture
- Server-side history management

**Evidence:** [Headless connectors audit](headless_connectors.md#2-codex-cli-connector)

---

## Test Evidence Analysis

### Session Continuation Tests
**File:** `tests/test_session_continuation.py` (from branch `session-continuation-pytest-simulated-connectors`)

**Key Findings:**
- ✅ All connectors maintain session IDs across multiple execute() calls
- ✅ Session isolation works correctly between different chat/role pairs  
- ✅ Recovery after process restart functions properly
- ❌ Tests focus on session persistence, not context passing

**Test Coverage:**
```python
# Example test showing session continuity
async def test_acp_session_persistence():
    connector = QwenACPConnector()
    await connector.launch(command, prompt)
    
    response1 = await connector.execute("Hello")
    response2 = await connector.execute("How are you?")
    
    # Session ID remains constant
    assert connector.session_id is not None
```

### Core Engine Tests
**File:** `tests/test_ncrew_core.py`

**Key Findings:**
- ✅ Autonomous cycle termination works correctly
- ✅ Role processing order maintained
- ❌ No tests verify full context passing to agents

---

## Discrepancies vs Desired Behavior

### Current: Delta-Based Context
```python
# Current implementation in engine.py
new_messages = conversation[last_seen_index:]
role_prompt, has_updates = self._format_conversation_for_role(
    new_messages, role, chat_id
)
```

### Desired: Full History Context
```python
# Desired implementation
full_conversation = await self.storage.load_conversation(chat_id)
role_prompt, has_updates = self._format_conversation_for_role(
    full_conversation, role, chat_id
)
```

### Impact Analysis

| Aspect | Current | Desired | Impact of Gap |
|--------|---------|---------|---------------|
| **Context Scope** | New messages only | Complete conversation | Agents lose early context |
| **Decision Coherence** | Limited to recent turns | Full decision history | Inconsistent responses |
| **Reference Ability** | Cannot reference old messages | Can reference any message | Limited problem-solving |
| **Token Usage** | Efficient | Higher | Cost vs capability trade-off |
| **Memory Growth** | Controlled | Unlimited | Scalability concerns |

---

## Prioritized Remediation Steps

### Priority 1: Core Engine Fix (Critical)

**Issue:** Delta-only context in `_process_with_role()`  
**File:** `app/core/engine.py` (lines 520-532)  
**Effort:** 2-3 days  
**Impact:** Enables full-history context for all agents

**Implementation:**
```python
# Replace delta extraction with full history
async def _process_with_role(self, chat_id: int, role: RoleConfig) -> str:
    # Load FULL conversation instead of delta
    conversation = await self.storage.load_conversation(chat_id)
    
    # Format complete history for role
    role_prompt, has_updates = self._format_conversation_for_role(
        conversation, role, chat_id  # Full conversation, not delta
    )
    
    # Remove role_last_seen_index tracking
    # Each agent gets complete context every time
```

### Priority 2: Storage Layer Enhancement (High)

**Issue:** Conversation truncation loses early context  
**File:** `app/storage/file_storage.py` (lines 500-503)  
**Effort:** 1-2 days  
**Impact:** Prevents context loss in long conversations

**Implementation Options:**
1. **Increase limit:** Raise `MAX_CONVERSATION_LENGTH` to 200-500
2. **Smart truncation:** Keep first N + last M messages
3. **Summary approach:** Summarize early messages, keep recent ones

### Priority 3: Configuration Options (Medium)

**Issue:** No control over context passing strategy  
**File:** `app/config.py`  
**Effort:** 1 day  
**Impact:** Provides flexibility for different use cases

**Implementation:**
```python
class Config:
    # Context strategy options
    CONTEXT_STRATEGY = "full_history"  # or "delta_only"
    MAX_CONVERSATION_LENGTH = 200
    CONTEXT_SUMMARY_LENGTH = 100
```

### Priority 4: Enhanced Testing (Medium)

**Issue:** Tests don't verify context passing  
**Files:** `tests/test_session_continuation.py`  
**Effort:** 2-3 days  
**Impact:** Ensures fix works correctly

**Implementation:**
```python
async def test_full_history_context():
    # Verify agents receive complete conversation
    # Check that early messages are included in prompts
    # Validate context coherence across turns
```

### Priority 5: Performance Optimization (Low)

**Issue:** Full history increases token usage  
**Files:** All connector files  
**Effort:** 3-5 days  
**Impact:** Reduces costs while maintaining capability

**Implementation:**
- Context summarization for very long conversations
- Smart context windowing
- Token usage monitoring

---

## Implementation Roadmap

### Phase 1: Core Fix (Week 1)
1. Modify `engine.py` to pass full conversation history
2. Remove `role_last_seen_index` tracking
3. Update prompt formatting for full context
4. Add comprehensive tests

### Phase 2: Storage Enhancement (Week 2)  
1. Increase conversation length limits
2. Implement smart truncation strategy
3. Add backup and recovery mechanisms
4. Performance testing

### Phase 3: Configuration & Monitoring (Week 3)
1. Add context strategy configuration
2. Implement token usage tracking
3. Add context length monitoring
4. Create admin controls

### Phase 4: Optimization (Week 4)
1. Implement context summarization
2. Add performance optimizations
3. Create usage analytics
4. Documentation updates

---

## Risk Assessment

### High Risks
1. **Token Cost Explosion:** Full history increases API costs
   - **Mitigation:** Implement token monitoring and limits
   - **Fallback:** Configurable context strategy

2. **Performance Degradation:** Larger prompts slow response time
   - **Mitigation:** Async processing and timeout management
   - **Monitoring:** Response time tracking

### Medium Risks
1. **Context Window Limits:** Agents may exceed token limits
   - **Mitigation:** Smart truncation and summarization
   - **Detection:** Pre-execution token counting

2. **Memory Usage:** Larger conversation storage
   - **Mitigation:** Efficient storage formats
   - **Monitoring:** Storage usage tracking

### Low Risks
1. **Backward Compatibility:** Existing workflows may break
   - **Mitigation:** Feature flags and gradual rollout
   - **Testing:** Comprehensive regression tests

---

## Success Criteria

### Functional Requirements
- ✅ All agents receive complete conversation history
- ✅ Session continuity maintained across restarts
- ✅ Context coherence in multi-turn dialogues
- ✅ No regression in existing functionality

### Non-Functional Requirements  
- ✅ Response time < 30 seconds for typical conversations
- ✅ Token usage within acceptable limits
- ✅ Memory usage scales linearly with conversation length
- ✅ No data loss during system restarts

### Test Coverage
- ✅ Unit tests for context passing logic
- ✅ Integration tests for multi-agent conversations
- ✅ Performance tests for large conversations
- ✅ Recovery tests for session interruptions

---

## Conclusion

The session audit reveals that while NeuroCrewLab has robust session management infrastructure, the core context passing mechanism needs fundamental restructuring. The current delta-based approach prevents agents from maintaining coherent long-term conversations, directly impacting user requirements for team discussion and session reuse.

**Recommended Action:** Implement Priority 1 fix (core engine modification) immediately, as it addresses the fundamental architectural gap. This single change will enable full-history context for all agents without requiring connector-level modifications.

**Long-term Vision:** With the core fix in place, NeuroCrewLab will achieve true multi-agent conversational continuity, enabling sophisticated team-based problem solving that maintains context across all participants.

---

## Supporting Documents

1. [Context Pipeline Analysis](context_pipeline.md) - Detailed flow analysis
2. [ACP Connectors Audit](acp_connectors.md) - OpenCode/Qwen/Gemini session handling  
3. [Headless Connectors Audit](headless_connectors.md) - Claude/Codex session handling
4. [User Stories](../USER_STORIES.md) - Complete requirements specification
5. [Session Continuation Tests](../../tests/test_session_continuation.py) - Test evidence
6. [Core Engine Tests](../../tests/test_ncrew_core.py) - Engine behavior verification

---

**Report prepared by:** Session Audit Team  
**Review status:** Ready for implementation  
**Next steps:** Begin Priority 1 core engine modification