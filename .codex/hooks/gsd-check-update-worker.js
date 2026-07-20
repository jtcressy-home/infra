#!/usr/bin/env node
// gsd-hook-version: 1.7.0
// Background worker spawned by gsd-check-update.js (SessionStart hook).

'use strict';

const fs = require('fs');
const path = require('path');
const { isSemverNewer } = require('../gsd-core/bin/lib/semver-compare.cjs');
const { checkLatestVersion } = require('../gsd-core/bin/check-latest-version.cjs');
const { PACKAGE_NAME } = require('../gsd-core/bin/lib/package-identity.cjs');

let MANAGED_HOOKS = [];
try {
  ({ MANAGED_HOOKS } = require('./managed-hooks-registry.cjs'));
} catch (e) {
  // Stale-hook detection is optional; update checks still work without the registry.
}

const cacheFile = process.env.GSD_CACHE_FILE;
const projectVersionFile = process.env.GSD_PROJECT_VERSION_FILE;
const globalVersionFile = process.env.GSD_GLOBAL_VERSION_FILE;

let installed = '0.0.0';
let configDir = '';
try {
  if (fs.existsSync(projectVersionFile)) {
    installed = fs.readFileSync(projectVersionFile, 'utf8').trim();
    configDir = path.dirname(path.dirname(projectVersionFile));
  } else if (fs.existsSync(globalVersionFile)) {
    installed = fs.readFileSync(globalVersionFile, 'utf8').trim();
    configDir = path.dirname(path.dirname(globalVersionFile));
  }
} catch (e) {}

const staleHooks = [];
if (configDir) {
  const hooksDir = path.join(configDir, 'hooks');
  try {
    const hookFiles = fs.readdirSync(hooksDir).filter((file) => MANAGED_HOOKS.includes(file));
    for (const hookFile of hookFiles) {
      try {
        const content = fs.readFileSync(path.join(hooksDir, hookFile), 'utf8');
        const versionMatch = content.match(/(?:\/\/|#) gsd-hook-version:\s*(.+)/);
        if (!versionMatch) {
          staleHooks.push({ file: hookFile, hookVersion: 'unknown', installedVersion: installed });
        } else {
          const hookVersion = versionMatch[1].trim();
          if (isSemverNewer(installed, hookVersion) && !hookVersion.includes('{{')) {
            staleHooks.push({ file: hookFile, hookVersion, installedVersion: installed });
          }
        }
      } catch (e) {}
    }
  } catch (e) {}
}

let latest = null;
try {
  const result = checkLatestVersion();
  if (result && result.ok) latest = result.version;
} catch (e) {}

const result = {
  update_available: latest && isSemverNewer(latest, installed),
  installed,
  latest: latest || 'unknown',
  checked: Math.floor(Date.now() / 1000),
  stale_hooks: staleHooks.length > 0 ? staleHooks : undefined,
  package_name: PACKAGE_NAME,
};

if (cacheFile) {
  try {
    fs.writeFileSync(cacheFile, JSON.stringify(result));
  } catch (e) {}
}
