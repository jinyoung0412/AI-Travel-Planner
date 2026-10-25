// Node 22+ asynchronous ESM resolver hook, registered by the offline preload.
import {createRequire} from 'node:module';
const {isDotenv, esmSource} = createRequire(import.meta.url)('./offline_dotenv.cjs');
const stubURL = 'data:text/javascript,' + encodeURIComponent(esmSource);
let roots = [];

export function initialize(data) {
  roots = data.roots;
}

export async function resolve(specifier, context, nextResolve) {
  if (isDotenv(specifier, roots)) return {url: stubURL, shortCircuit: true};
  const resolved = await nextResolve(specifier, context);
  return isDotenv(resolved.url, roots) ? {url: stubURL, shortCircuit: true} : resolved;
}
