// Test-only preload, inherited by npm, Node test workers and gateway smoke.
// Guard installed dotenv CJS/ESM entry points before evaluating their code.
// Node contract tests need literal loopback TCP; resolver queries are forbidden.
const Module = require('node:module');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {isDotenv, stub} = require('./offline_dotenv.cjs');
const roots = [];
try {
  const projectRequire = Module.createRequire(path.resolve(__dirname, '../../NodeJs_server/server.js'));
  roots.push(path.dirname(projectRequire.resolve('dotenv/package.json')));
} catch {
  // Bare installed-package names are still guarded when dependencies are absent.
}
const load = Module._load;
Module._load = function(name, ...args) {
  if (isDotenv(name, roots)) return stub;
  let resolved;
  try { resolved = Module._resolveFilename(name, ...args); } catch {
    return load.call(this, name, ...args);
  }
  if (isDotenv(resolved, roots)) return stub;
  return load.call(this, name, ...args);
};
const forbidden = () => { throw new Error('External calls are forbidden in offline checks'); };
const local = host => host === '127.0.0.1' || host === '::1';
const net = require('node:net');
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function(...args) {
  // Node internal callers may pass its normalized [options, callback] pair.
  const first = Array.isArray(args[0]) ? args[0][0] : args[0];
  const host = typeof first === 'object' ? first.host :
    (typeof args[1] === 'string' ? args[1] : undefined);
  if (!local(host)) forbidden();
  return connect.apply(this, args);
};
const dns = require('node:dns');
const lookup = dns.lookup;
dns.lookup = function(host, ...args) {
  if (!local(host)) forbidden();
  return lookup.call(this, host, ...args);
};
const promises = require('node:dns/promises');
const promiseLookup = promises.lookup;
promises.lookup = function(host, ...args) {
  if (!local(host)) forbidden();
  return promiseLookup.call(this, host, ...args);
};
// c-ares queries bypass net.Socket and the JavaScript dgram implementation.
// Cover both already-bound default functions and newly constructed resolvers.
for (const api of [dns, promises, dns.Resolver.prototype, promises.Resolver.prototype]) {
  for (const name of Object.getOwnPropertyNames(api)) {
    if (/^resolve/.test(name) || name === 'reverse' || name === 'lookupService') api[name] = forbidden;
  }
}
require('node:dgram').Socket.prototype.send = forbidden;
// Named ESM builtin imports must see the guarded functions too.
Module.syncBuiltinESMExports();
Module.register('./offline_loader.mjs', pathToFileURL(__filename), {data: {roots}});
