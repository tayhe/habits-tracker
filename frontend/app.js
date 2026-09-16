import { createApp, ref, reactive, computed, onMounted, onUnmounted, nextTick } from './vendor/vue.esm-browser.prod.js';

const API = '/api/v1';

// Subject configurations
const SUBJECT_INFO = {
  '英语': { class: 'english', emoji: '🔤', color: '#2563EB' },
  '数学': { class: 'math', emoji: '🧮', color: '#D97706' },
  '语文': { class: 'chinese', emoji: '📝', color: '#059669' }
};

// Date helper utilities
function pad(n) {
  return String(n).padStart(2, '0');
}

function formatDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function isSameDay(a, b) {
  if (!a || !b) return false;
  return a.getFullYear() === b.getFullYear() &&
         a.getMonth() === b.getMonth() &&
         a.getDate() === b.getDate();
}

function getWeekStart(d) {
  const date = new Date(d);
  const day = date.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  return addDays(date, day === 0 ? -6 : 1 - day); // Monday (ISO week start)
}

function getWeekStr(d) {
  const weekStart = getWeekStart(d);
  const yearStart = new Date(d.getFullYear(), 0, 1);
  const yearStartMonday = getWeekStart(yearStart);
  const weekNum = Math.ceil(((weekStart - yearStartMonday) / 86400000 + 1) / 7);
  return `${d.getFullYear()}-W${pad(weekNum)}`;
}

function parseWeekStr(s) {
  const [y, w] = s.split('-W').map(Number);
  const jan4 = new Date(y, 0, 4);
  const jan4Mon = getWeekStart(jan4);
  return addDays(jan4Mon, (w - 1) * 7);
}

function formatWeekDisplay(weekStr, start) {
  const [year, w] = weekStr.split('-W');
  const end = addDays(start, 6);
  const fmt = d => `${d.getMonth() + 1}月${d.getDate()}日`;
  return `${year}年第${parseInt(w, 10)}周（${fmt(start)}-${fmt(end)}）`;
}

function getDayName(d) {
  const names = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return names[d.getDay()];
}

function formatMD(d) {
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function progressEmoji(completed, total) {
  if (total === 0) return '😿';
  const rate = completed / total;
  if (rate >= 1.0) return '😺🎉';
  if (rate >= 0.75) return '😺';
  if (rate >= 0.5) return '😸';
  if (rate >= 0.25) return '😼';
  if (rate > 0) return '😾';
  return '😿';
}

function progressBar(completed, total, maxLen = 15) {
  if (total === 0) return '░'.repeat(Math.min(4, maxLen));
  const len = Math.min(total, maxLen);
  const filled = Math.round((completed / total) * len);
  return '▓'.repeat(filled) + '░'.repeat(len - filled);
}

// Main Vue Application
const app = createApp({
  setup() {
    // Global state
    const currentUser = ref(null);
    const currentView = ref('daily');
    const config = ref({ editable_day_window: 7 });

    // Toast
    const toast = reactive({ show: false, message: '', timer: null });
    function showToast(msg) {
      if (toast.timer) clearTimeout(toast.timer);
      toast.message = msg;
      toast.show = true;
      toast.timer = setTimeout(() => {
        toast.show = false;
      }, 2500);
    }

    // Generic API request
    async function api(method, path, body) {
      const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin'
      };
      if (body) opts.body = JSON.stringify(body);
      try {
        const resp = await fetch(API + path, opts);
        if (resp.status === 401) {
          currentUser.value = null;
          return null;
        }
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          showToast(err.detail || '请求失败');
          return null;
        }
        const text = await resp.text();
        return text ? JSON.parse(text) : true;
      } catch (err) {
        showToast('网络请求异常');
        return null;
      }
    }

    // Auth & Login Form
    const loginForm = reactive({ username: '', password: '' });
    async function handleLogin() {
      const data = await api('POST', '/auth/login', {
        username: loginForm.username,
        password: loginForm.password
      });
      if (data && data.user) {
        currentUser.value = data.user;
        loginForm.password = '';
        switchView('daily');
      }
    }

    async function handleLogout() {
      await api('POST', '/auth/logout');
      currentUser.value = null;
      location.reload();
    }

    // Change Password Modal
    const pwdModal = reactive({
      show: false,
      oldPwd: '',
      newPwd: '',
      confirmPwd: ''
    });

    function openPwdModal() {
      pwdModal.oldPwd = '';
      pwdModal.newPwd = '';
      pwdModal.confirmPwd = '';
      pwdModal.show = true;
    }

    function closePwdModal() {
      pwdModal.show = false;
    }

    async function handlePwdSubmit() {
      if (!pwdModal.oldPwd || !pwdModal.newPwd || !pwdModal.confirmPwd) {
        showToast('请填写所有字段');
        return;
      }
      if (pwdModal.newPwd.length < 6) {
        showToast('新密码至少需要6个字符');
        return;
      }
      if (pwdModal.newPwd !== pwdModal.confirmPwd) {
        showToast('两次输入的新密码不一致');
        return;
      }
      const resp = await api('PUT', '/auth/password', {
        old_password: pwdModal.oldPwd,
        new_password: pwdModal.newPwd
      });
      if (resp) {
        showToast('密码修改成功');
        pwdModal.show = false;
      }
    }

    // View Navigation
    function switchView(view) {
      currentView.value = view;
      if (view === 'ambition') loadAmbition();
      else if (view === 'daily') loadDaily();
      else if (view === 'weekly') loadWeekly();
      else if (view === 'trend') loadTrend();
      else if (view === 'tasks') loadTaskMgmt();
    }

    // --- Ambition View ---
    const ambitionTasks = ref([]);
    const ambitionTotals = computed(() => {
      let totalTasks = ambitionTasks.value.length;
      let totalMinPerWeek = 0;
      let totalMaxReward = 0;
      ambitionTasks.value.forEach(t => {
        totalMinPerWeek += t.weekly_min;
        totalMaxReward += t.reward * t.weekly_min;
      });
      return { totalTasks, totalMinPerWeek, totalMaxReward };
    });

    const ambitionBySubject = computed(() => {
      const subjects = ['英语', '数学', '语文'];
      return subjects.map(subject => {
        const info = SUBJECT_INFO[subject];
        const tasks = ambitionTasks.value.filter(t => t.subject === subject);
        let subjectMaxReward = 0;
        tasks.forEach(t => { subjectMaxReward += t.reward * t.weekly_min; });
        return { subject, info, tasks, subjectMaxReward };
      }).filter(s => s.tasks.length > 0);
    });

    async function loadAmbition() {
      const tasks = await api('GET', '/tasks');
      if (tasks) ambitionTasks.value = tasks;
    }

    // --- Daily View ---
    const currentWeekStart = ref(getWeekStart(new Date()));
    const weekData = ref(null);

    const weekRangeText = computed(() => {
      if (!currentWeekStart.value) return '';
      return formatWeekDisplay(getWeekStr(currentWeekStart.value), currentWeekStart.value);
    });

    const dailySubjectTasks = computed(() => {
      const map = { '英语': [], '数学': [], '语文': [] };
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
        const isEditable = currentUser.value?.role === 'parent' || (d >= threeDaysAgo && d <= today);
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
        const dDate = new Date(d.date);
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

    async function loadDaily() {
      if (!currentWeekStart.value) currentWeekStart.value = getWeekStart(new Date());
      currentWeekStart.value.setHours(0, 0, 0, 0);
      await loadWeekData();
    }

    async function loadWeekData() {
      const dateStr = formatDate(currentWeekStart.value);
      const data = await api('GET', `/records/week?date=${dateStr}`);
      if (data) weekData.value = data;
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

    // --- Weekly View ---
    const currentWeekStr = ref(getWeekStr(new Date()));
    const weeklySummary = ref(null);

    const weekRangeText2 = computed(() => {
      if (!currentWeekStr.value) return '';
      const monday = parseWeekStr(currentWeekStr.value);
      return formatWeekDisplay(currentWeekStr.value, monday);
    });

    async function loadWeekly() {
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
      loadWeekly();
    }

    // --- Trend View ---
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
      const weekStart = new Date(w.week_start);
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

    // --- Task Management View (Parent Only) ---
    const taskList = ref([]);
    async function loadTaskMgmt() {
      const tasks = await api('GET', '/tasks');
      if (tasks) taskList.value = tasks;
    }

    async function saveTask(task) {
      const update = {
        name: task.name,
        subject: task.subject,
        reward: parseFloat(task.reward),
        weekly_min: parseInt(task.weekly_min, 10)
      };
      const resp = await api('PUT', `/tasks/${task.task_id}`, update);
      if (resp) showToast('保存成功');
    }

    async function deleteTask(task) {
      if (!confirm('确认删除？')) return;
      const resp = await api('DELETE', `/tasks/${task.task_id}`);
      if (resp) {
        showToast('已删除');
        loadTaskMgmt();
      }
    }

    async function addTask() {
      const name = prompt('任务名称：');
      if (!name) return;
      const subject = prompt('科目（英语/数学/语文）：');
      if (!['英语', '数学', '语文'].includes(subject)) {
        showToast('科目无效');
        return;
      }
      const reward = parseFloat(prompt('单次收益：') || '0.1');
      const weekly_min = parseInt(prompt('周最低次数：') || '3', 10);
      const resp = await api('POST', '/tasks', {
        task_id: 'custom_' + crypto.randomUUID(),
        subject,
        name,
        reward,
        weekly_min,
        sort_weight: 0
      });
      if (resp) {
        showToast('创建成功');
        loadTaskMgmt();
      }
    }

    // Document click to dismiss dropdown
    function onDocClick(e) {
      if (activeDropdown.visible && !e.target.closest('.multiselect-dropdown') && !e.target.closest('.chip-add')) {
        closeDropdown();
      }
    }

    onMounted(async () => {
      document.addEventListener('click', onDocClick);
      const cfg = await api('GET', '/config');
      if (cfg) config.value = cfg;
      const me = await api('GET', '/auth/me');
      if (me) {
        currentUser.value = me;
        switchView('daily');
      }
    });

    onUnmounted(() => {
      document.removeEventListener('click', onDocClick);
    });

    return {
      // Globals & auth
      currentUser,
      currentView,
      config,
      toast,
      loginForm,
      handleLogin,
      handleLogout,
      pwdModal,
      openPwdModal,
      closePwdModal,
      handlePwdSubmit,
      switchView,
      SUBJECT_INFO,
      // Helpers
      formatMD,
      getDayName,
      progressEmoji,
      progressBar,
      // Ambition
      ambitionTotals,
      ambitionBySubject,
      // Daily
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
      // Weekly
      currentWeekStr,
      weeklySummary,
      weekRangeText2,
      navWeekly,
      // Trend
      trendWeeks,
      trendData,
      fulfillment,
      maxTrendReward,
      bestWeek,
      worstWeek,
      formatTrendWeek,
      loadTrend,
      toggleFulfillment,
      // Task mgmt
      taskList,
      saveTask,
      deleteTask,
      addTask
    };
  }
});

app.mount('#appRoot');
