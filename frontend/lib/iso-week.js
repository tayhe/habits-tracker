// ISO-8601 week label helpers.
//
// Kept as a standalone module so `scripts/parity_check.mjs` can import the exact
// implementation the app runs and diff it against `backend/weeks.py`.

import { addDays, pad } from './dates.js';

/** Date -> 'YYYY-Www' (ISO week label, timezone-independent). */
export function getWeekStr(d) {
  const target = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNr = (target.getUTCDay() + 6) % 7; // Monday = 0
  target.setUTCDate(target.getUTCDate() - dayNr + 3); // Thursday in target week determines ISO week & year
  const firstThursday = target.valueOf();
  target.setUTCMonth(0, 1);
  if (target.getUTCDay() !== 4) {
    target.setUTCMonth(0, 1 + ((4 - target.getUTCDay()) + 7) % 7);
  }
  const weekNum = 1 + Math.ceil((firstThursday - target) / 604800000);
  const year = new Date(firstThursday).getUTCFullYear();
  return `${year}-W${pad(weekNum)}`;
}

/** 'YYYY-Www' -> Monday of that week (local Date). */
export function parseWeekStr(s) {
  const [y, w] = s.split('-W').map(Number);
  const jan4 = new Date(y, 0, 4);
  const jan4Day = (jan4.getDay() + 6) % 7;
  const week1Mon = addDays(jan4, -jan4Day);
  return addDays(week1Mon, (w - 1) * 7);
}
