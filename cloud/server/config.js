'use strict';
/* 运行配置：全部来自环境变量，带默认值（REQ-000015）。 */

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');                 // cloud/
const REPO_ROOT = path.join(ROOT, '..');                 // 仓库根：本地单机版所在

function loadConfig(env = process.env) {
  const port = Number(env.PORT || 8090);
  const dataDir = path.resolve(env.DATA_DIR || path.join(ROOT, 'data'));
  const registerCode = env.REGISTER_CODE || 'dev-code';
  const rateLimitPerMin = Number(env.RATE_LIMIT_PER_MIN || 30);
  const radiusDefault = 200;
  const radiusMax = Number(env.RADIUS_MAX || 400);

  const problems = [];
  if (!Number.isInteger(port) || port < 1 || port > 65535) problems.push(`PORT 非法：${env.PORT}`);
  if (!Number.isFinite(rateLimitPerMin) || rateLimitPerMin < 1) problems.push('RATE_LIMIT_PER_MIN 非法');
  if (!Number.isFinite(radiusMax) || radiusMax < radiusDefault) problems.push('RADIUS_MAX 不能小于默认半径');

  return {
    port,
    dataDir,
    cardDir: path.join(dataDir, 'cards'),
    dbPath: path.join(dataDir, 'world.db'),
    registerCode,
    usingDefaultCode: !env.REGISTER_CODE,
    rateLimitPerMin,
    radiusDefault,
    radiusMax,
    appRoot: ROOT,           // cloud/：多人版前端（play/）与包文件
    repoRoot: REPO_ROOT,     // 仓库根：本地单机版静态文件
    version: require('../package.json').version,
    problems,
  };
}

/** 确保数据目录存在且可写；失败时抛出可读原因（REQ-000015 边界）。 */
function ensureDataDir(cfg) {
  try {
    fs.mkdirSync(cfg.cardDir, { recursive: true });
    const probe = path.join(cfg.dataDir, '.write-probe');
    fs.writeFileSync(probe, 'ok');
    fs.unlinkSync(probe);
  } catch (e) {
    const err = new Error(`数据目录不可写：${cfg.dataDir}（${e.code || e.message}）`);
    err.code = 'DATA_DIR_UNWRITABLE';
    throw err;
  }
}

module.exports = { loadConfig, ensureDataDir, ROOT };
