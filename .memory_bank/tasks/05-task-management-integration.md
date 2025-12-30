---
title: Task Management Integration
stage: Specification
status: New
priority: High
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
---

# Description

Обновить команду запуска задачи для использования промптов этапа. При запуске задачи подставлять пути к файлам задачи и шаблонов в промпты.

## Requirements

### Промпты этапов

Промпты находятся в `~/.ncrew/stage_prompts/`:
- `specification.md` - Промпт для этапа Specification
- `plan.md` - Промпт для этапа Plan
- `implementation.md` - Промпт для этапа Implementation
- `verification.md` - Промпт для этапа Verification

### Команда запуска

**Текущая команда:**
```bash
opencode -m <provider>/<name> run "прочитай и выполни задачу из файла <path>"
```

**Новая команда:**
1. Прочитать промпт для текущего этапа из `~/.ncrew/stage_prompts/{stage}.md`
2. Заменить переменные:
   - `{task_file}` → путь к файлу задачи
   - `{spec_template}` → путь к шаблону спецификации (если есть)
   - `{plan_template}` → путь к шаблону плана (если есть)
3. Выполнить команду:
```bash
opencode -m <provider>/<name> run "<промпт>"
```

### Пример

**Задача:**
- `stage: Specification`
- `taskId: task-auth`
- Путь к задаче: `.memory_bank/tasks/task-auth.md`

**Промпт (specification.md):**
```markdown
Прочитай и выполни задачу из файла {task_file}.

На выходе должна быть спецификация по шаблону ~/.ncrew/templates/spec.md.
```

**Результирующая команда:**
```bash
opencode -m opencode/claude-sonnet-4-5 run "Прочитай и выполни задачу из файла .memory_bank/tasks/task-auth.md.

На выходе должна быть спецификация по шаблону ~/.ncrew/templates/spec.md."
```

### Требования к реализации

1. **Backend**
   - Функция для чтения промпта этапа
   - Функция для замены переменных в промпте
   - Обновить команду запуска задачи для использования промпта
   - Добавить этап в имя файла логов (уже реализовано в Задаче 4)

2. **Frontend**
   - Нет изменений (логика на backend)

3. **UI**
   - Нет изменений

## Dependencies

- Зависит от: Задача 1 (System Settings), Задача 2 (Templates and Prompts), Задача 3 (Workflow)
- Блокирует: -

## Acceptance Criteria

- ✅ При запуске задачи используется промпт соответствующего этапа
- ✅ Переменные в промпте заменяются на реальные значения
- ✅ Команда opencode содержит корректный промпт
- ✅ Если промпт не найден - используется дефолтный промпт
- ✅ Логи содержат информацию о использованном промпте
