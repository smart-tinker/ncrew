const os = require('os');
const path = require('path');
const fs = require('fs-extra');

function getNcrewHomeDir() {
  return path.join(os.homedir(), '.ncrew');
}

function getSettingsDir() {
  return path.join(getNcrewHomeDir(), 'settings');
}

function getProjectsDir() {
  return path.join(getSettingsDir(), 'projects');
}

function getTemplatesDir() {
  return path.join(getNcrewHomeDir(), 'templates');
}

function getStagePromptsDir() {
  return path.join(getNcrewHomeDir(), 'stage_prompts');
}

function getModelsCacheFile() {
  return path.join(getSettingsDir(), 'models-cache.json');
}

function getTaskLogsDir(projectPath) {
  return path.join(projectPath, '.memory_bank', 'logs');
}

module.exports = {
  getNcrewHomeDir,
  getSettingsDir,
  getProjectsDir,
  getTemplatesDir,
  getStagePromptsDir,
  getModelsCacheFile,
  getTaskLogsDir
};
