# План реализации: Task Management Integration

**Основан на спецификации:** `.memory_bank/tasks/05-task-management-integration.md`  
**Дата:** 2025-12-30  
**Версия:** 1.0  
**Статус:** Done  
**Статус:** Implementation

## Обзор

Обновить команду запуска задачи для использования промптов этапа.

## Предварительные требования

### Текущее состояние
- Промпты этапов созданы в `~/.ncrew/stage_prompts/`
- Команда запуска задачи использует фиксированный промпт
- Формат имени файла логов: `{taskId}-{stage}-{timestamp}.log`

### Зависимости
- Задача 1 (System Settings) - Done
- Задача 2 (Templates and Prompts) - Done
- Задача 3 (Workflow) - Done
- Задача 4 (Timer and Logs) - Done

## Этап 1: Backend - промпты этапов

### 1.1. Функция чтения промпта этапа

**Файл:** `backend/server.js`

**Задача:**
1. Создать функцию `getStagePrompt(stage)`
2. Читает промпт из `~/.ncrew/stage_prompts/{stage}.md`
3. Если файл не существует - возвращает дефолтный промпт

**Псевдокод:**
```javascript
async function getStagePrompt(stage) {
  const promptPath = path.join(getNcrewHomeDir(), 'stage_prompts', `${stage.toLowerCase()}.md`);
  
  try {
    if (await fs.pathExists(promptPath)) {
      return await fs.readFile(promptPath, 'utf-8');
    }
  } catch (error) {
    console.error(`Error reading stage prompt for ${stage}:`, error);
  }
  
  return 'Please read and execute the task.';
}
```

### 1.2. Функция замены переменных

**Файл:** `backend/server.js`

**Задача:**
1. Создать функцию `replaceVariables(prompt, variables)`
2. Заменяет `{task_file}` на путь к файлу задачи
3. Заменяет `{spec_template}` на путь к шаблону спецификации
4. Заменяет `{plan_template}` на путь к шаблону плана

**Псевдокод:**
```javascript
function replaceVariables(prompt, variables) {
  let result = prompt;
  
  for (const [key, value] of Object.entries(variables)) {
    const regex = new RegExp(`\\{${key}\\}`, 'g');
    result = result.replace(regex, value);
  }
  
  return result;
}
```

### 1.3. Обновить команду запуска задачи

**Файл:** `backend/server.js`

**Задача:**
1. Получить промпт для текущего этапа
2. Заменить переменные:
   - `{task_file}` → `.memory_bank/tasks/${taskId}.md`
   - `{spec_template}` → `~/.ncrew/templates/spec.md` (для Specification этапа)
   - `{plan_template}` → `~/.ncrew/templates/plan.md` (для Plan этапа)
3. Использовать промпт в команде opencode
4. Добавить информацию о промпте в логи

**Псевдокод:**
```javascript
const stagePrompt = await getStagePrompt(frontmatter.stage);
const variables = {
  task_file: taskRelativePath
};

if (frontmatter.stage === 'Specification') {
  variables.spec_template = path.join(getNcrewHomeDir(), 'templates/spec.md');
} else if (frontmatter.stage === 'Plan') {
  variables.plan_template = path.join(getNcrewHomeDir(), 'templates/plan.md');
}

const finalPrompt = replaceVariables(stagePrompt, variables);

// Логирование промпта
logStream.write(`[NCrew] Stage: ${frontmatter.stage}\n`);
logStream.write(`[NCrew] Prompt:\n${finalPrompt}\n`);
logStream.write('---\n');

// Команда opencode
const process = spawn('opencode', ['-m', modelFullName, 'run', finalPrompt], {
  cwd: worktreePath
});
```

## Этап 2: Обновление задачи

### 2.1. Обновить фронтматтер задачи

**Файл:** `.memory_bank/tasks/05-task-management-integration.md`

**Изменения:**
```yaml
---
title: Task Management Integration
stage: Implementation
status: In Progress
priority: High
agenticHarness: opencode
modelProvider: opencode
modelName: claude-sonnet-4-5
specification: ../specs/20251230-06-task-management-integration.md
plan: ../plans/20251230-06-task-management-integration.md
---
```

## Этап 3: Тестирование

### 3.1. Проверка чтения промпта

**Сценарии:**
1. Проверить, что промпт для Specification читается корректно
2. Проверить, что промпт для Plan читается корректно
3. Проверить, что несуществующий этап возвращает дефолтный промпт

### 3.2. Проверка замены переменных

**Сценарии:**
1. Проверить, что `{task_file}` заменяется на путь к файлу задачи
2. Проверить, что `{spec_template}` заменяется на путь к шаблону (для Specification)
3. Проверить, что `{plan_template}` заменяется на путь к шаблону (для Plan)

### 3.3. Проверка команды запуска

**Сценарии:**
1. Запустить задачу на этапе Specification
2. Проверить логи - должен быть промпт для Specification
3. Запустить задачу на этапе Plan
4. Проверить логи - должен быть промпт для Plan

## Порядок выполнения

### Последовательные задачи:
1. Этап 1 (Backend)
2. Этап 2 (обновление задачи)
3. Этап 3 (тестирование)

## Приемочные критерии

После реализации проверить:
- ✅ При запуске задачи используется промпт соответствующего этапа
- ✅ Переменные в промпте заменяются на реальные значения
- ✅ Команда opencode содержит корректный промпт
- ✅ Логи содержат информацию о использованном промпте
- ✅ Если промпт не найден - используется дефолтный промпт

## Примечания

1. **Дефолтный промпт:** "Please read and execute the task."
2. **Имена файлов:** Этапы в именах файлов промптов в нижнем регистре (specification.md, plan.md и т.д.)
3. **Логирование:** Добавлять промпт в логи для отладки
4. **Обработка ошибок:** Логировать ошибки чтения промпта

## Зависимости

### Требуется проверить:
- `fs.pathExists()` используется для проверки существования файлов
- `fs.readFile()` используется для чтения промптов
- Шаблоны существуют в `~/.ncrew/templates/`

## Время реализации

Оценка:
- Этап 1 (Backend): 1 час
- Этап 2 (обновление задачи): 5 минут
- Этап 3 (тестирование): 15 минут

**Итого:** 1.25 часа
