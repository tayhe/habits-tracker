import { computed, ref } from '../vendor/vue.esm-browser.prod.js';
import { addDays, parseDateLocal } from '../lib/dates.js';

// 征途 (Trend): 多周趋势对比、最好/最差周与"爸爸兑现"勾选。
export function createTrendView(ctx) {
  const { api } = ctx;

  const trendWeeks = ref(8);
  const trendData = ref([]);
  const fulfillment = ref({});

  const maxTrendReward = computed(() => {
    if (!trendData.value.length) return 1;
    return Math.max(...trendData.value.map(w => w.total_reward), 1);
  });

  const bestWeek = computed(() => {
    if (!trendData.value.length) return null;
    return trendData.value.reduce((a, b) => (a.tasks_met > b.tasks_met ? a : b));
  });

  const worstWeek = computed(() => {
    if (!trendData.value.length) return null;
    return trendData.value.reduce((a, b) => (a.tasks_met < b.tasks_met ? a : b));
  });

  function formatTrendWeek(w) {
    const weekStart = parseDateLocal(w.week_start);
    const weekEnd = addDays(weekStart, 6);
    const weekNum = parseInt(w.week.split('-W')[1], 10);
    return `${weekStart.getFullYear()}年第${weekNum}周（${weekStart.getMonth() + 1}月${weekStart.getDate()}日-${weekEnd.getMonth() + 1}月${weekEnd.getDate()}日）`;
  }

  async function loadTrend() {
    const data = await api('GET', `/summary/multi-week?weeks=${trendWeeks.value}`);
    if (!data) return;
    trendData.value = data;
    const weekStrs = data.map(w => w.week);
    if (weekStrs.length > 0) {
      const fulfillData = await api('GET', `/summary/fulfillment?weeks=${weekStrs.join('&weeks=')}`);
      fulfillment.value = fulfillData || {};
    } else {
      fulfillment.value = {};
    }
  }

  async function toggleFulfillment(week) {
    const targetState = !fulfillment.value[week];
    const resp = await api('PUT', `/summary/fulfillment?week=${week}&fulfilled=${targetState}`);
    if (resp) {
      fulfillment.value[week] = targetState;
    }
  }

  return {
    load: loadTrend,
    bindings: {
      trendWeeks,
      trendData,
      fulfillment,
      maxTrendReward,
      bestWeek,
      worstWeek,
      formatTrendWeek,
      loadTrend,
      toggleFulfillment,
    },
  };
}
