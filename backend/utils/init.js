const fs = require('fs-extra');
const {
  getSettingsDir,
  getProjectsDir,
  getTemplatesDir,
  getStagePromptsDir,
  getModelsCacheFile
} = require('./paths');

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

  console.log('NCrew structure initialized successfully');
}

module.exports = {
  initNcrewStructure
};
