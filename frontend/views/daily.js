import { computed, reactive, ref } from '../vendor/vue.esm-browser.prod.js';
import {
  addDays, formatDate, formatWeekDisplay, getWeekStart, isSameDay, parseDateLocal,
} from '../lib/dates.js';
import { getWeekStr } from '../lib/iso-week.js';

// 每日捕猎 (Daily): 一周网格、打卡与"补录任务"浮层。
export function createDailyView(ctx) {
  const { api, config, currentUser, showToast, subjectList } = ctx;

  const currentWeekStart = ref(getWeekStart(new Date()));
  const weekData = ref(null);

  const weekRangeText = computed(() => {
    if (!currentWeekStart.value) return '';
    return formatWeekDisplay(getWeekStr(currentWeekStart.value), currentWeekStart.value);
  });

  const dailySubjectTasks = computed(() => {
    const map = {};
    subjectList.value.forEach(subject => { map[subject] = []; });
    if (weekData.value && weekData.value.days && weekData.value.days.length > 0) {
      weekData.value.days[0].records.forEach(rec => {
        if (map[rec.subject]) {
          map[rec.subject].push({ task_id: rec.task_id, name: rec.task_name, subject: rec.subject });
        }
      });
    }
    return map;
  });

  const dailyDays = computed(() => {
    if (!currentWeekStart.value) return [];
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const days = [];
    const windowDays = config.value.editable_day_window || 7;
    const threeDaysAgo = addDays(today, -(windowDays - 1));

    for (let i = 0; i < 7; i++) {
      const d = addDays(currentWeekStart.value, i);
      d.setHours(0, 0, 0, 0);
      const dateStr = formatDate(d);
      const isToday = isSameDay(d, today);
      const isEditable = (currentUser.value?.role === 'parent' || d >= threeDaysAgo) && d <= today;
      const isHistory = currentUser.value?.role !== 'parent' && d < threeDaysAgo;
      const dayData = weekData.value?.days ? weekData.value.days[i] : null;

      days.push({
        date: d,
        dateStr,
        isToday,
        isEditable,
        isHistory,
        dayData,
        dayEarn: dayData ? dayData.total_reward : 0,
        completedCount: dayData ? dayData.completed_count : 0,
        totalCount: dayData ? dayData.total_count : 0
      });
    }
    return days;
  });

  const todayFooter = computed(() => {
    if (!weekData.value?.days) return { completedCount: 0, totalCount: 0, earn: 0, hasData: false };
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayData = weekData.value.days.find(d => {
      const dDate = parseDateLocal(d.date);
      dDate.setHours(0, 0, 0, 0);
      return isSameDay(dDate, today);
    });
    return {
      completedCount: todayData ? todayData.completed_count : 0,
      totalCount: todayData ? todayData.total_count : 0,
      earn: weekData.value.expected_earn || 0,
      hasData: !!todayData
    };
  });

  function isTaskCompleted(day, taskId) {
    if (!day.dayData || !day.dayData.records) return false;
    const rec = day.dayData.records.find(r => r.task_id === taskId);
    return rec ? rec.completed : false;
  }

  async function loadWeekData() {
    const dateStr = formatDate(currentWeekStart.value);
    const data = await api('GET', `/records/week?date=${dateStr}`);
    if (data) weekData.value = data;
  }

  async function load() {
    if (!currentWeekStart.value) currentWeekStart.value = getWeekStart(new Date());
    currentWeekStart.value.setHours(0, 0, 0, 0);
    await loadWeekData();
  }

  function navWeek(action) {
    closeDropdown();
    if (action === 'home') {
      currentWeekStart.value = getWeekStart(new Date());
    } else if (action === 'prev') {
      currentWeekStart.value = addDays(currentWeekStart.value, -7);
    } else if (action === 'next') {
      currentWeekStart.value = addDays(currentWeekStart.value, 7);
    }
    currentWeekStart.value.setHours(0, 0, 0, 0);
    loadWeekData();
  }

  // Dropdown for adding tasks
  const activeDropdown = reactive({
    visible: false,
    date: '',
    subject: '',
    top: 0,
    left: 0,
    tasks: []
  });

  function openDropdown(dateStr, subject, event) {
    if (activeDropdown.visible && activeDropdown.date === dateStr && activeDropdown.subject === subject) {
      closeDropdown();
      return;
    }
    const dayData = weekData.value?.days.find(d => d.date === dateStr);
    const allTasks = weekData.value?.days[0]?.records.filter(r => r.subject === subject) || [];

    // Uncompleted tasks for this day
    const uncompleted = allTasks.filter(task => {
      const rec = dayData ? dayData.records.find(r => r.task_id === task.task_id) : null;
      return rec ? !rec.completed : true;
    });

    if (uncompleted.length === 0) return;

    const rect = event.currentTarget.getBoundingClientRect();
    let top = rect.bottom + 4;
    let left = rect.left;

    if (top + 200 > window.innerHeight) {
      top = rect.top - 200 - 4;
    }
    if (left + 160 > window.innerWidth) {
      left = window.innerWidth - 170;
    }

    activeDropdown.date = dateStr;
    activeDropdown.subject = subject;
    activeDropdown.top = top;
    activeDropdown.left = left;
    activeDropdown.tasks = uncompleted;
    activeDropdown.visible = true;
  }

  function closeDropdown() {
    activeDropdown.visible = false;
  }

  async function toggleRecord(dateStr, taskId, currentStatus, isEditable) {
    if (!isEditable) return;
    closeDropdown();
    const resp = await api('PUT', '/records', {
      date: dateStr,
      task_id: taskId,
      completed: !currentStatus
    });
    if (resp) {
      await loadWeekData();
      showToast(!currentStatus ? '已完成 ✓' : '已取消');
    }
  }

  async function selectDropdownTask(taskId) {
    const dateStr = activeDropdown.date;
    closeDropdown();
    const resp = await api('PUT', '/records', {
      date: dateStr,
      task_id: taskId,
      completed: true
    });
    if (resp) {
      await loadWeekData();
      showToast('已完成 ✓');
    }
  }

  // Document click to dismiss the dropdown (registered by app.js).
  function docClick(e) {
    if (activeDropdown.visible && !e.target.closest('.multiselect-dropdown') && !e.target.closest('.chip-add')) {
      closeDropdown();
    }
  }

  return {
    load,
    docClick,
    bindings: {
      currentWeekStart,
      weekRangeText,
      dailySubjectTasks,
      dailyDays,
      isTaskCompleted,
      todayFooter,
      navWeek,
      activeDropdown,
      openDropdown,
      closeDropdown,
      toggleRecord,
      selectDropdownTask,
    },
  };
}
