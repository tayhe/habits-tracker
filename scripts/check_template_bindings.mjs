// Static guard: every identifier the template uses must be exposed by setup().
//
// The Vue app compiles `index.html` in the browser, so a typo like
// `v-for="sub in weeklySubject"` would only surface as a silently empty UI.
// This script cross-checks template expressions against the object returned
// from `setup()` in app.js, plus `v-for` locals and a whitelist of globals.
//
//     node scripts/check_template_bindings.mjs

import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
const appJs = readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');

// --- identifiers returned from setup() --------------------------------------
const returnBlock = appJs.match(/return\s*\{([\s\S]*?)\n    \};/);
if (!returnBlock) {
  console.error('could not locate the setup() return object in app.js');
  process.exit(1);
}
const exposed = new Set(
  [...returnBlock[1].matchAll(/([A-Za-z_$][\w$]*)\s*(?:,|$)/gm)].map(m => m[1]),
);

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
  console.error('Template references bindings that setup() does not expose:');
  for (const [name, ctx] of missing) console.error(`  ${name}  <-  ${ctx}`);
  process.exit(1);
}

console.log(
  `template bindings OK: ${expressions.length} expressions, `
  + `${exposed.size} exposed bindings, ${locals.size} v-for local(s)`,
);
