const fs = require('fs-extra');
const {
  getSettingsDir,
  getProjectsDir,
  getTemplatesDir,
  getStagePromptsDir,
  getModelsCacheFile
} = require('./paths');

const DEFAULT_TEMPLATES = {
  'task.md': `---\n` +
    `title: Task Title\n` +
    `stage: Specification\n` +
    `status: New\n` +
    `priority: Medium\n` +
    `agenticHarness: opencode\n` +
    `modelProvider: opencode\n` +
    `modelName: claude-sonnet-4-5\n` +
    `---\n\n` +
    `# Description\n\n` +
    `Task description...\n\n` +
    `## Requirements\n\n` +
    `1. Requirement 1\n` +
    `2. Requirement 2\n\n` +
    `## Dependencies\n\n` +
    `- Зависит от: -\n` +
    `- Блокирует: -\n\n` +
    `## Acceptance Criteria\n\n` +
    `- ✅ AC 1\n` +
    `- ✅ AC 2\n`,
  'spec.md': `# Спецификация: <название>\n\n` +
    `**Имя:** <имя>  \n` +
    `**Дата:** <дата>  \n` +
    `**Версия:** <версия>  \n` +
    `**Статус:** <статус>\n\n` +
    `## Обзор\n\n` +
    `Краткое описание фичи.\n\n` +
    `## User Stories\n\n` +
    `### US-X.1: Название\n` +
    `Как **<роль>**, я хочу <действие>, чтобы <цель>.\n\n` +
    `## Требования\n\n` +
    `### Функциональные требования\n` +
    `...\n\n` +
    `### Нефункциональные требования\n` +
    `...\n\n` +
    `## Приемочные критерии\n\n` +
    `1. ✅ Критерий 1\n` +
    `2. ✅ Критерий 2\n`,
  'plan.md': `# План реализации: <название>\n\n` +
    `**Основан на спецификации:** <путь к спецификации>  \n` +
    `**Дата:** <дата>  \n` +
    `**Версия:** <версия>\n\n` +
    `## Обзор\n\n` +
    `План описывает реализацию фичи.\n\n` +
    `## Предварительные требования\n\n` +
    `...\n\n` +
    `## Этапы\n\n` +
    `### Этап 1: <название>\n` +
    `...\n\n` +
    `## Приемочные критерии\n\n` +
    `...\n`
};

const DEFAULT_STAGE_PROMPTS = {
  'specification.md': `Прочитай и выполни задачу из файла {task_file}.\n\n` +
    `На выходе должна быть спецификация по шаблону {spec_template}.\n\n` +
    `Спецификация должна содержать:\n` +
    `- User Stories (минимум 2-3 истории)\n` +
    `- Функциональные требования\n` +
    `- Нефункциональные требования\n` +
    `- Приемочные критерии (минимум 5 критериев)\n`,
  'plan.md': `Прочитай спецификацию из файла {task_file}.\n\n` +
    `Создай план реализации по шаблону {plan_template}.\n\n` +
    `План должен содержать:\n` +
    `- Предварительные требования\n` +
    `- Этапы (минимум 3 этапа)\n` +
    `- Детализированные задачи\n` +
    `- Приемочные критерии для каждого этапа\n`,
  'implementation.md': `Прочитай план реализации из файла {task_file}.\n\n` +
    `Реализуй функционал согласно плану.\n\n` +
    `Требования к реализации:\n` +
    `- Код должен следовать конвенциям проекта\n` +
    `- Использовать существующие библиотеки\n` +
    `- Писать тесты\n` +
    `- Обновлять документацию\n`,
  'verification.md': `Прочитай реализацию из файла {task_file}.\n\n` +
    `Проверь, что все приемочные критерии спецификации выполнены.\n\n` +
    `Проверки:\n` +
    `1. Функциональные тесты\n` +
    `2. Unit тесты\n` +
    `3. Integration тесты\n` +
    `4. Линтинг и типизация\n` +
    `5. Документация\n\n` +
    `Результат проверки: PASS/FAIL с объяснением.\n`
};

async function ensureFileIfMissing(filePath, content) {
  if (await fs.pathExists(filePath)) return;
  await fs.writeFile(filePath, content, 'utf-8');
}

async function initNcrewStructure() {
  console.log('Initializing NCrew structure...');

  const dirs = [
    getSettingsDir(),
    getProjectsDir(),
    getTemplatesDir(),
    getStagePromptsDir()
  ];

  for (const dir of dirs) {
    await fs.ensureDir(dir);
    console.log(`  Created directory: ${dir}`);
  }

  const cacheFile = getModelsCacheFile();
  if (!await fs.pathExists(cacheFile)) {
    await fs.writeJson(cacheFile, {});
    console.log(`  Created cache file: ${cacheFile}`);
  }

  const templatesDir = getTemplatesDir();
  for (const [fileName, content] of Object.entries(DEFAULT_TEMPLATES)) {
    const filePath = require('path').join(templatesDir, fileName);
    await ensureFileIfMissing(filePath, content);
    console.log(`  Ensured template: ${filePath}`);
  }

  const promptsDir = getStagePromptsDir();
  for (const [fileName, content] of Object.entries(DEFAULT_STAGE_PROMPTS)) {
    const filePath = require('path').join(promptsDir, fileName);
    await ensureFileIfMissing(filePath, content);
    console.log(`  Ensured stage prompt: ${filePath}`);
  }

  console.log('NCrew structure initialized successfully');
}

module.exports = {
  initNcrewStructure
};
