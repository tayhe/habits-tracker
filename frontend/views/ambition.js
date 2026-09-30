import { computed, ref } from '../vendor/vue.esm-browser.prod.js';

// 喵的雄心 (Ambition): 全部任务与"每周最高可得"总览。
export function createAmbitionView(ctx) {
  const { api, subjectList, SUBJECT_INFO } = ctx;

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
    return subjectList.value.map(subject => {
      const info = SUBJECT_INFO[subject];
      const tasks = ambitionTasks.value.filter(t => t.subject === subject);
      let subjectMaxReward = 0;
      tasks.forEach(t => { subjectMaxReward += t.reward * t.weekly_min; });
      return { subject, info, tasks, subjectMaxReward };
    }).filter(s => s.tasks.length > 0);
  });

  async function load() {
    const tasks = await api('GET', '/tasks');
    if (tasks) ambitionTasks.value = tasks;
  }

  return {
    load,
    bindings: {
      ambitionTotals,
      ambitionBySubject,
    },
  };
}
