# Session Audit Documentation

Этот каталог содержит технические аудиты управления сессиями и состоянием в различных коннекторах NeuroCrew Lab.

## Цель

Документировать и анализировать:
- Управление session identifiers (`--session-id`, `--resume`, `thread_id`)
- Передачу истории диалогов (full history vs deltas)
- Lifecycle процессов и сессий
- Обработку failures и recovery механизмы
- Риски и пробелы в continuous-session behavior

## Содержимое

### [headless_connectors.md](./headless_connectors.md)

**Дата:** 21 ноября 2024

Подробный анализ non-ACP коннекторов:
- `app/connectors/claude_cli_connector.py`
- `app/connectors/codex_cli_connector.py`

**Основные разделы:**
1. Session management механизмы
2. History management стратегии
3. Process model (stateless subprocess)
4. State machines для каждого коннектора
5. Сравнение с ACP коннекторами
6. Интеграция с NeuroCrew Engine
7. Protocol notes (CLI флаги, JSON events)
8. Concrete risks & gaps
9. Рекомендации по улучшению

**Ключевые находки:**
- Headless коннекторы используют stateless subprocess model (в отличие от долгоживущих ACP процессов)
- История управляется полностью на стороне CLI через session identifiers
- Критическая зависимость от external state management
- Отсутствие recovery механизмов при потере сессии
- Gaps в тестировании failure scenarios

## Использование

### Для разработчиков

Перед изменением коннекторов:
1. Прочитайте соответствующий аудит
2. Учитывайте описанные state machines
3. Проверяйте влияние на session continuity
4. Добавляйте тесты для edge cases из секции "Risks & Gaps"

### Для code review

При ревью изменений в коннекторах:
1. Сверьте изменения с задокументированным поведением
2. Проверьте что новая логика не нарушает session management
3. Убедитесь что добавлены тесты для критических сценариев
4. Обновите аудит если поведение изменилось

### Для troubleshooting

При проблемах с сессиями:
1. Найдите соответствующий коннектор в аудите
2. Посмотрите state machine диаграмму
3. Проверьте секцию "Failure Handling"
4. Следуйте рекомендациям из "Recommendations"

## Формат аудита

Каждый аудит следует структуре:

```markdown
1. Executive Summary
2. Per-Connector Analysis
   - Session Management
   - History Management
   - Process Model
   - Session Priming
   - Failure Handling
   - Reset/Shutdown Behavior
   - State Machine
   - Test Coverage
3. Comparison with Other Approaches
4. Integration Context
5. Protocol Notes
6. Concrete Risks & Gaps
7. Recommendations (Short/Medium/Long-term)
8. Conclusion with Action Items
```

## Обновление документации

При изменении коннекторов:

```bash
# 1. Внесите изменения в код
git add app/connectors/

# 2. Обновите соответствующий аудит
vim docs/session_audit/headless_connectors.md

# 3. Отметьте изменения
git add docs/session_audit/

# 4. Commit с ссылкой на аудит
git commit -m "Fix session recovery in Claude connector

See docs/session_audit/headless_connectors.md section 8.2
Implements retry logic for --resume failures"
```

## История версий

| Дата | Документ | Версия | Описание |
|------|----------|--------|----------|
| 2024-11-21 | headless_connectors.md | 1.0 | Начальный аудит Claude и Codex коннекторов |

## Планируемые аудиты

- [ ] `acp_connectors.md` - анализ OpenCode, Qwen, Gemini ACP connectors
- [ ] `session_storage.md` - анализ FileStorage и conversation persistence
- [ ] `engine_state_management.md` - анализ NeuroCrewLab session tracking

---

**Поддержка:** Вопросы и предложения по улучшению аудитов приветствуются в issues.
