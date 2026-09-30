// Dependency-free unit checks for the pure frontend helpers.
//
// Runs in plain Node (no browser, no test framework):
//     TZ=Asia/Shanghai node scripts/frontend_unit.mjs
//
// Covered:
//   - humanDetail(): FastAPI 422 payload -> readable toast (N-01)
//   - parseDateLocal(): 'YYYY-MM-DD' parsed as *local* date (P2-08)
//   - ISO week label round trip + known boundary labels (T-06)
//   - progressEmoji(): tier boundaries match backend/rules.py

import assert from 'node:assert/strict';

import { formatDate, getWeekStart, parseDateLocal } from '../frontend/lib/dates.js';
import { humanDetail } from '../frontend/lib/errors.js';
import { getWeekStr, parseWeekStr } from '../frontend/lib/iso-week.js';
import { progressEmoji } from '../frontend/lib/progress.js';

let count = 0;
function check(name, actual, expected) {
  assert.deepEqual(actual, expected, `${name}: got ${JSON.stringify(actual)}`);
  count++;
}

// --- humanDetail -------------------------------------------------------------
check('detail: plain string passes through',
  humanDetail('用户名或密码错误'), '用户名或密码错误');
check('detail: null becomes empty',
  humanDetail(null), '');
check('detail: empty array',
  humanDetail([]), '请求参数不合法');
check('detail: explicit null field',
  humanDetail([{ type: 'value_error', loc: ['body'], msg: "Value error, 字段 'reward' 不能为 null" }]),
  "字段 'reward' 不能为 null");
check('detail: missing required field',
  humanDetail([{ type: 'missing', loc: ['body', 'reward'], msg: 'Field required' }]),
  '单次收益为必填项');
check('detail: unknown field name falls back to raw key',
  humanDetail([{ type: 'missing', loc: ['body', 'something_else'], msg: 'Field required' }]),
  'something_else为必填项');
check('detail: out of range',
  humanDetail([{ type: 'greater_than_equal', loc: ['body', 'weekly_min'], msg: 'Greater than or equal to 1', ctx: { ge: 1 } }]),
  '周最低次数不能小于 1');
check('detail: never dumps raw JSON',
  humanDetail([{ type: 'whatever', loc: ['body'], msg: 'boom' }]).includes('['),
  false);

// --- parseDateLocal ----------------------------------------------------------
check('date: round trip', formatDate(parseDateLocal('2026-03-05')), '2026-03-05');
check('date: parsed at local midnight', parseDateLocal('2026-03-05').getHours(), 0);
check('date: week start of a parsed date stays on a Monday',
  getWeekStart(parseDateLocal('2026-03-05')).getDay(), 1);
check('date: leap day', formatDate(parseDateLocal('2024-02-29')), '2024-02-29');

// --- ISO week labels ---------------------------------------------------------
check('week: 2021-01-01 belongs to 2020-W53', getWeekStr(new Date(2021, 0, 1)), '2020-W53');
check('week: 2026-01-04 opens 2026-W01', getWeekStr(new Date(2026, 0, 4)), '2026-W01');
check('week: monday of 2026-W01', formatDate(parseWeekStr('2026-W01')), '2025-12-29');

for (let year = 2020; year <= 2030; year++) {
  for (let week = 1; week <= 52; week++) {
    const label = `${year}-W${String(week).padStart(2, '0')}`;
    const monday = parseWeekStr(label);
    if (getWeekStr(monday) === label) {
      check(`week: round trip ${label}`, formatDate(getWeekStart(monday)), formatDate(monday));
    }
  }
}

// --- progress emoji ----------------------------------------------------------
check('emoji: empty', progressEmoji(0, 0), '😿');
check('emoji: none done', progressEmoji(0, 5), '😿');
check('emoji: 1/5 (0.2)', progressEmoji(1, 5), '😾');
check('emoji: 2/5 (0.4)', progressEmoji(2, 5), '😼');
check('emoji: 3/5 (0.6)', progressEmoji(3, 5), '😸');
check('emoji: 4/5 (0.8)', progressEmoji(4, 5), '😺');
check('emoji: 5/5 (1.0)', progressEmoji(5, 5), '😺🎉');
check('emoji: exact 0.75 boundary', progressEmoji(3, 4), '😺');
check('emoji: exact 0.25 boundary', progressEmoji(1, 4), '😼');

console.log(`frontend unit OK: ${count} assertions`);
