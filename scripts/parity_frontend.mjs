// Print canonical outputs of the *browser* date/week/emoji logic, mirroring
// scripts/parity_backend.py line for line so the two can be diffed.
//
// Run directly:  node scripts/parity_frontend.mjs

import { addDays, formatDate, getWeekStart } from '../frontend/lib/dates.js';
import { getWeekStr, parseWeekStr } from '../frontend/lib/iso-week.js';
import { progressEmoji } from '../frontend/lib/progress.js';

const START = new Date(2020, 0, 1);
const DAYS = 1500;
const YEAR_RANGE = [];
for (let y = 2020; y <= 2030; y++) YEAR_RANGE.push(y);

const lines = [];

// 1) ISO week label + Monday/Sunday range for 1500 consecutive days.
let d = START;
for (let i = 0; i < DAYS; i++) {
  const monday = getWeekStart(d);
  const sunday = addDays(monday, 6);
  lines.push(`week ${formatDate(d)} ${getWeekStr(d)} ${formatDate(monday)} ${formatDate(sunday)}`);
  d = addDays(d, 1);
}

// 2) Week-label parsing. `parseWeekStr` itself is unvalidated (it is always fed
//    a label produced by getWeekStr in the app), so validation is reproduced by
//    round-tripping: a label is valid iff it maps back to itself.
for (const year of YEAR_RANGE) {
  for (let week = 1; week <= 52; week++) {
    const label = `${year}-W${String(week).padStart(2, '0')}`;
    const monday = parseWeekStr(label);
    const sunday = addDays(monday, 6);
    if (getWeekStr(monday) !== label) {
      lines.push(`parse ${label} invalid`);
    } else {
      lines.push(`parse ${label} ok ${formatDate(monday)} ${formatDate(sunday)}`);
    }
  }
}

// 3) Progress emoji tiers over the full (completed, total) grid.
for (let total = 0; total <= 16; total++) {
  for (let completed = 0; completed <= total; completed++) {
    lines.push(`emoji ${completed}/${total} ${progressEmoji(completed, total)}`);
  }
}

process.stdout.write(`${lines.join('\n')}\n`);
