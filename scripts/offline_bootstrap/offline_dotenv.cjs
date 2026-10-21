// Module identity only: no dotenv implementation or configuration file is read.
const path = require('node:path');
const {fileURLToPath} = require('node:url');

function isDotenv(identifier, roots) {
  if (typeof identifier !== 'string') return false;
  if (identifier === 'dotenv' || identifier.startsWith('dotenv/')) return true;
  let filename = identifier;
  if (identifier.startsWith('file:')) {
    try { filename = fileURLToPath(identifier); } catch { return false; }
  }
  if (!path.isAbsolute(filename)) return false;
  const normalized = path.resolve(filename).replaceAll('\\', '/');
  if (/(?:^|\/)node_modules\/dotenv(?:\/|$)/.test(normalized)) return true;
  return roots.some(root => {
    const relative = path.relative(root, filename);
    return relative === '' || (!relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative));
  });
}

const config = () => ({parsed: {}});
const parse = () => ({});
const populate = () => {};
const decrypt = () => '';
const stub = {config, configDotenv: config, parse, populate, decrypt, _configVault: config};
const esmSource = `
export const config = () => ({parsed:{}});
export const configDotenv = config;
export const parse = () => ({});
export const populate = () => {};
export const decrypt = () => '';
export const _configVault = config;
export default {config,configDotenv,parse,populate,decrypt,_configVault};
`;

module.exports = {isDotenv, stub, esmSource};
