// Static guard: every identifier the template uses must be exposed by setup().
//
// The Vue app compiles `index.html` in the browser, so a typo like
// `v-for="sub in weeklySubject"` would only surface as a silently empty UI.
// This script cross-checks template expressions against the union of:
//
//   - the object returned from `setup()` in frontend/app.js (globals/helpers)
//   - each view module's `bindings: { ... }` object in frontend/views/*.js
//
// plus `v-for` locals and a whitelist of globals. Object bodies are found by
// brace matching (strings and comments skipped), and binding objects must use
// shorthand properties (`foo,` not `foo: bar,`).
//
//     node scripts/check_template_bindings.mjs

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = join(dirname(fileURLToPath(import.meta.url)), '..', 'frontend');
const html = readFileSync(join(FRONTEND, 'index.html'), 'utf8');
const appJs = readFileSync(join(FRONTEND, 'app.js'), 'utf8');

function skipString(source, i) {
  const quote = source[i];
  for (let j = i + 1; j < source.length; j++) {
    if (source[j] === '\\') { j += 1; continue; }
    if (source[j] === quote) return j;
  }
  return source.length;
}

/** Body (without braces) of the balanced object starting at `openIndex`. */
function objectBody(source, openIndex) {
  let depth = 0;
  for (let i = openIndex; i < source.length; i++) {
    const ch = source[i];
    if (ch === "'" || ch === '"' || ch === '`') { i = skipString(source, i); continue; }
    if (ch === '/' && source[i + 1] === '/') { i = source.indexOf('\n', i); if (i < 0) break; continue; }
    if (ch === '/' && source[i + 1] === '*') { i = source.indexOf('*/', i + 2); if (i < 0) break; i += 1; continue; }
    if (ch === '{') depth += 1;
    else if (ch === '}') { depth -= 1; if (depth === 0) return source.slice(openIndex + 1, i); }
  }
  return null;
}

function shorthandIdentifiers(body) {
  const noComments = body.replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/^\s*\/\/.*$/gm, ' ');
  // Drop spreads (`...viewBindings`) first: the identifier of a spread is not
  // an exposed binding, and view bindings are unioned from views/*.js anyway.
  const noSpreads = noComments.replace(/\.\.\.[A-Za-z_$][\w$]*/g, ' ');
  return [...noSpreads.matchAll(/([A-Za-z_$][\w$]*)\s*(?:,|$)/gm)].map(m => m[1]);
}

function locate(source, pattern, what) {
  const hits = [...source.matchAll(pattern)];
  if (hits.length === 0) {
    console.error(`could not locate ${what}`);
    process.exit(1);
  }
  return hits;
}

const exposed = new Set();
// Files scanned for the `name: value` hint below.
const sources = [{ name: 'frontend/app.js', source: appJs }];

// --- setup() return object --------------------------------------------------
// After the view split app.js has exactly one `return {` (the setup surface);
// before it, inner computeds also return objects, so fall back to the last one
// -- setup()'s return is the final statement of the component.
const viewsDir = join(FRONTEND, 'views');
const viewsExist = existsSync(viewsDir);
const returns = [...appJs.matchAll(/\breturn\s*\{/g)];
if (returns.length === 0) {
  console.error('could not locate `return {` in frontend/app.js');
  process.exit(1);
}
if (viewsExist && returns.length !== 1) {
  console.error(`frontend/app.js must contain exactly one \`return {\` (found ${returns.length}); `
    + 'view state belongs in frontend/views/*.js');
  process.exit(1);
}
const lastReturn = returns[returns.length - 1];
const setupBody = objectBody(appJs, appJs.indexOf('{', lastReturn.index));
if (setupBody === null) { console.error('unbalanced object in app.js setup() return'); process.exit(1); }
for (const id of shorthandIdentifiers(setupBody)) exposed.add(id);

// --- each view module's bindings object ------------------------------------
if (viewsExist) {
  for (const file of readdirSync(viewsDir).filter(f => f.endsWith('.js')).sort()) {
    const source = readFileSync(join(viewsDir, file), 'utf8');
    sources.push({ name: `frontend/views/${file}`, source });
    const hits = locate(source, /\bbindings\s*:\s*\{/g, `bindings: { in views/${file}`);
    for (const hit of hits) {
      const body = objectBody(source, source.indexOf('{', hit.index));
      if (body === null) { console.error(`unbalanced bindings object in views/${file}`); process.exit(1); }
      for (const id of shorthandIdentifiers(body)) exposed.add(id);
    }
  }
}

// --- expressions appearing in the template ----------------------------------
const GLOBALS = new Set([
  'Math', 'Date', 'Number', 'String', 'Array', 'Object', 'JSON', 'Boolean',
  'parseInt', 'parseFloat', 'isNaN', 'isFinite', 'encodeURIComponent',
  'undefined', 'true', 'false', 'null',
  'console', 'window', 'document', 'crypto', 'confirm', 'prompt',
  'setTimeout', 'clearTimeout',
]);
const KEYWORDS = new Set(['in', 'of', 'typeof', 'instanceof', 'new', 'void', 'delete']);

const expressions = [];
for (const m of html.matchAll(/\{\{([\s\S]*?)\}\}/g)) expressions.push(m[1]);
for (const m of html.matchAll(/\s(?:v-[a-z-]+|@[a-z-]+|:[a-z-]+(?:\.[a-z-]+)?)\s*=\s*"([^"]*)"/g)) {
  expressions.push(m[1]);
}

// v-for introduces locals: `v-for="sub in weeklySubjects"` -> sub,
// `v-for="(t, i) in xs"` -> t, i
const locals = new Set();
for (const m of html.matchAll(/v-for\s*=\s*"([^"]*)"/g)) {
  const head = m[1].split(/\s+in\s+|\s+of\s+/)[0];
  for (const name of head.matchAll(/[A-Za-z_$][\w$]*/g)) locals.add(name[0]);
}

function stripLiterals(expr) {
  return expr
    .replace(/'[^']*'/g, ' ')
    .replace(/"[^"]*"/g, ' ')
    .replace(/`[^`]*`/g, ' ');
}

const missing = new Map();
for (const raw of expressions) {
  const expr = stripLiterals(raw);
  const ident = /\b[A-Za-z_$][\w$]*/g;
  let m;
  while ((m = ident.exec(expr)) !== null) {
    const name = m[0];
    const before = expr.slice(0, m.index).trimEnd();
    const after = expr.slice(m.index + name.length).trimStart();
    // `foo.bar` / `foo?.bar` -> `bar` is a property, not a binding.
    if (/[.]$/.test(before) || before.endsWith('?.')) continue;
    // `key: value` in an object literal (also covers the true branch of a
    // ternary, which is a documented blind spot for this heuristic).
    if (/^:/.test(after)) continue;
    if (exposed.has(name) || locals.has(name) || GLOBALS.has(name) || KEYWORDS.has(name)) continue;
    missing.set(name, raw.trim());
  }
}

if (missing.size > 0) {
  console.error('Template references bindings that setup()/views do not expose:');
  for (const [name, ctx] of missing) {
    console.error(`  ${name}  <-  ${ctx}`);
    // Most common cause after the view split: `foo: bar` inside a bindings
    // object, which shorthand extraction deliberately ignores.
    for (const file of sources) {
      if (new RegExp(`\\b${name}\\s*:`).test(file.source)) {
        console.error(`    hint: \`${name}: ...\` is only collected as shorthand; write \`${name},\``
          + ` in ${file.name}`);
        break;
      }
    }
  }
  process.exit(1);
}

console.log(
  `template bindings OK: ${expressions.length} expressions, `
  + `${exposed.size} exposed bindings, ${locals.size} v-for local(s)`,
);
