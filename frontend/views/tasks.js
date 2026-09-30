import { ref } from '../vendor/vue.esm-browser.prod.js';

// 军令状 (Task management, parent only): 增删改任务。
export function createTasksView(ctx) {
  const { api, showToast, subjectList } = ctx;

  const taskList = ref([]);

  async function load() {
    const tasks = await api('GET', '/tasks');
    if (tasks) taskList.value = tasks;
  }

  async function saveTask(task) {
    const reward = parseFloat(task.reward);
    const weeklyMin = parseInt(task.weekly_min, 10);
    if (!Number.isFinite(reward) || reward < 0) {
      showToast('单次收益必须是大于或等于 0 的有效数字');
      return;
    }
    if (!Number.isInteger(weeklyMin) || weeklyMin < 1) {
      showToast('周最低次数必须是大于或等于 1 的整数');
      return;
    }
    const update = {
      name: task.name,
      subject: task.subject,
      reward: reward,
      weekly_min: weeklyMin
    };
    const resp = await api('PUT', `/tasks/${task.task_id}`, update);
    if (resp) showToast('保存成功');
  }

  async function deleteTask(task) {
    if (!confirm('确认删除？')) return;
    const resp = await api('DELETE', `/tasks/${task.task_id}`);
    if (resp) {
      showToast('已删除');
      load();
    }
  }

  async function addTask() {
    const name = prompt('任务名称：');
    if (!name) return;
    const subjects = subjectList.value;
    const subject = prompt(`科目（${subjects.join('/')}）：`);
    if (!subjects.includes(subject)) {
      showToast(`科目无效，必须是 ${subjects.join('、')} 之一`);
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
      load();
    }
  }

  return {
    load,
    bindings: {
      taskList,
      saveTask,
      deleteTask,
      addTask,
    },
  };
}
