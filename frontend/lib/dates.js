// Pure local-date helpers shared by the app and the parity check script.
//
// RULE: never call `new Date(string)` on a 'YYYY-MM-DD' value. JavaScript parses
// that as UTC midnight, which lands on the previous day in Asia/Shanghai.
// Always go through `parseDateLocal()` instead.

export function pad(n) {
  return String(n).padStart(2, '0');
}

export function formatDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 'YYYY-MM-DD' -> Date in the *local* timezone (not UTC midnight). */
export function parseDateLocal(s) {
  const [y, m, d] = String(s).split('-').map(Number);
  if (!y || !m || !d) throw new Error(`invalid date string: ${s}`);
  return new Date(y, m - 1, d);
}

export function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

export function isSameDay(a, b) {
  if (!a || !b) return false;
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth() === b.getMonth() &&
         a.getDate() === b.getDate();
}

/** Monday of the ISO week containing `d`. */
export function getWeekStart(d) {
  const date = new Date(d);
  const day = date.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  return addDays(date, day === 0 ? -6 : 1 - day);
}

export function formatWeekDisplay(weekStr, start) {
  const [year, w] = weekStr.split('-W');
  const end = addDays(start, 6);
  const fmt = d => `${d.getMonth() + 1}月${d.getDate()}日`;
  return `${year}年第${parseInt(w, 10)}周（${fmt(start)}-${fmt(end)}）`;
}

export function getDayName(d) {
  const names = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return names[d.getDay()];
}

export function formatMD(d) {
  return `${d.getMonth() + 1}/${d.getDate()}`;
}
