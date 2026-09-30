import { createApp, computed, onMounted, onUnmounted, reactive, ref } from './vendor/vue.esm-browser.prod.js';

// Pure helpers live in ./lib so that scripts/parity_check.mjs can import the
// exact implementation the browser runs and diff it against the Python side
// (backend/weeks.py / backend/rules.py).
import { formatMD, getDayName } from './lib/dates.js';
import { progressEmoji, progressBar } from './lib/progress.js';
import { humanDetail } from './lib/errors.js';

// View state lives in ./views/<view>.js. Each factory returns
// `{ load, bindings, docClick? }`: `load` is dispatched by switchView(),
// `bindings` is spread into the setup() return surface (that spread is what
// scripts/check_template_bindings.mjs reads together with every view file).
import { createAmbitionView } from './views/ambition.js';
import { createDailyView } from './views/daily.js';
import { createWeeklyView } from './views/weekly.js';
import { createTrendView } from './views/trend.js';
import { createTasksView } from './views/tasks.js';

const API = '/api/v1';

// Subject configurations (presentation only; the *list* of subjects comes from
// GET /config so backend and frontend cannot drift apart).
const SUBJECT_INFO = {
  '英语': { class: 'english', emoji: '🔤', color: '#2563EB' },
  '数学': { class: 'math', emoji: '🧮', color: '#D97706' },
  '语文': { class: 'chinese', emoji: '📝', color: '#059669' }
};

const DEFAULT_SUBJECTS = Object.keys(SUBJECT_INFO);
const SUBJECT_FALLBACK = { class: 'other', emoji: '📌', color: '#6B7280' };

// Main Vue Application
const app = createApp({
  setup() {
    // Global state
    const currentUser = ref(null);
    const currentView = ref('daily');
    const config = ref({ editable_day_window: 7, subjects: [] });

    // Canonical subject order/list comes from GET /config (backend owns it).
    // SUBJECT_INFO keys are only the offline fallback for styling.
    const subjectList = computed(() => (
      Array.isArray(config.value.subjects) && config.value.subjects.length
        ? config.value.subjects
        : DEFAULT_SUBJECTS
    ));
    const weeklySubjects = computed(() => [...subjectList.value, '总计']);

    // Make sure every server-side subject has presentation styles.
    function ensureSubjectStyles(subjects) {
      (subjects || []).forEach(s => {
        if (!(s in SUBJECT_INFO)) SUBJECT_INFO[s] = SUBJECT_FALLBACK;
      });
    }

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
          if (path.startsWith('/auth/login')) {
            const err = await resp.json().catch(() => ({}));
            showToast(humanDetail(err.detail) || '用户名或密码错误');
          }
          return null;
        }
        if (resp.status === 429) {
          const err = await resp.json().catch(() => ({}));
          showToast(humanDetail(err.detail) || '尝试次数过多，请稍后再试');
          return null;
        }
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          showToast(humanDetail(err.detail) || `请求失败 (${resp.status})`);
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

    // --- View modules -------------------------------------------------------
    const views = {
      ambition: createAmbitionView({ api, showToast, currentUser, config, subjectList, SUBJECT_INFO }),
      daily: createDailyView({ api, showToast, currentUser, config, subjectList }),
      weekly: createWeeklyView({ api }),
      trend: createTrendView({ api }),
      tasks: createTasksView({ api, showToast, subjectList }),
    };

    // View Navigation
    function switchView(view) {
      currentView.value = view;
      const mod = views[view];
      if (mod && mod.load) mod.load();
    }

    onMounted(async () => {
      document.addEventListener('click', views.daily.docClick);
      const cfg = await api('GET', '/config');
      if (cfg) {
        config.value = cfg;
        ensureSubjectStyles(cfg.subjects);
      }
      const me = await api('GET', '/auth/me');
      if (me) {
        currentUser.value = me;
        switchView('daily');
      }
    });

    onUnmounted(() => {
      document.removeEventListener('click', views.daily.docClick);
    });

    const viewBindings = Object.assign({}, ...Object.values(views).map(v => v.bindings));

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
      subjectList,
      weeklySubjects,
      // Helpers
      formatMD,
      getDayName,
      progressEmoji,
      progressBar,
      // Ambition / Daily / Weekly / Trend / Task management
      ...viewBindings,
    };
  }
});

app.mount('#appRoot');
