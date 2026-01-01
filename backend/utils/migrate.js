const path = require('path');
const fs = require('fs-extra');
const {
  getProjectsDir,
  getModelsCacheFile
} = require('./paths');

function getOldSettingsCandidates() {
  const cwd = process.cwd();

  return [
    // Common when starting backend from repo root: `node backend/server.js`
    path.join(cwd, 'settings'),
    // Common when starting backend from `backend/`: `node server.js`
    path.join(cwd, '..', 'settings'),
    // Fallback relative to this file's location
    path.join(__dirname, '..', '..', 'settings')
  ];
}

async function migrateOldSettings() {
  console.log('Checking for old settings to migrate...');

  const candidates = getOldSettingsCandidates();
  const oldSettingsDir = (await (async () => {
    for (const candidate of candidates) {
      try {
        if (await fs.pathExists(candidate)) {
          return candidate;
        }
      } catch {
        // ignore
      }
    }
    return null;
  })());
  const newSettingsDir = getProjectsDir();
  
  if (!oldSettingsDir) {
    console.log('  No old settings found');
    return;
  }
  
  // Migrate projects
  const oldProjectsDir = path.join(oldSettingsDir, 'projects');
  const newProjectsDir = newSettingsDir;
  
  if (await fs.pathExists(oldProjectsDir)) {
    await fs.copy(oldProjectsDir, newProjectsDir, { overwrite: true });
    console.log(`  Migrated projects: ${oldProjectsDir} -> ${newProjectsDir}`);
  }
  
  // Migrate models cache
  const oldCacheFile = path.join(oldSettingsDir, 'models-cache.json');
  const newCacheFile = getModelsCacheFile();
  
  if (await fs.pathExists(oldCacheFile)) {
    await fs.copy(oldCacheFile, newCacheFile, { overwrite: true });
    console.log(`  Migrated models cache: ${oldCacheFile} -> ${newCacheFile}`);
  }
  
  // Backup old settings
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupPath = path.join(
    path.dirname(oldSettingsDir),
    `${path.basename(oldSettingsDir)}-backup-${timestamp}`
  );
  
  await fs.copy(oldSettingsDir, backupPath, {
    filter: (src) => {
      const basename = path.basename(src);
      return basename !== 'backup' && !basename.startsWith('backup-');
    }
  });
  console.log(`  Created backup: ${backupPath}`);
  
  console.log('Settings migration completed');
}

module.exports = {
  migrateOldSettings
};
