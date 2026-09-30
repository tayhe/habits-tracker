import { computed, ref } from '../vendor/vue.esm-browser.prod.js';
import { addDays, formatWeekDisplay } from '../lib/dates.js';
import { getWeekStr, parseWeekStr } from '../lib/iso-week.js';

// 一周战果 (Weekly): 单周汇总、达标与表情。
export function createWeeklyView(ctx) {
  const { api } = ctx;

  const currentWeekStr = ref(getWeekStr(new Date()));
  const weeklySummary = ref(null);

  const weekRangeText2 = computed(() => {
    if (!currentWeekStr.value) return '';
    const monday = parseWeekStr(currentWeekStr.value);
    return formatWeekDisplay(currentWeekStr.value, monday);
  });

  async function load() {
    if (!currentWeekStr.value) currentWeekStr.value = getWeekStr(new Date());
    const data = await api('GET', `/summary/weekly?week=${currentWeekStr.value}`);
    if (data) weeklySummary.value = data;
  }

  function navWeekly(action) {
    if (action === 'home') {
      currentWeekStr.value = getWeekStr(new Date());
    } else if (action === 'prev') {
      const monday = parseWeekStr(currentWeekStr.value);
      currentWeekStr.value = getWeekStr(addDays(monday, -7));
    } else if (action === 'next') {
      const monday = parseWeekStr(currentWeekStr.value);
      currentWeekStr.value = getWeekStr(addDays(monday, 7));
    }
    load();
  }

  return {
    load,
    bindings: {
      currentWeekStr,
      weeklySummary,
      weekRangeText2,
      navWeekly,
    },
  };
}
