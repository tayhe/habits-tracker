// Error message normalization for API failures.
//
// FastAPI/Pydantic 422 responses look like
//   {detail: [{type: 'value_error', loc: ['body'], msg: "Value error, ..."}]}
// and would otherwise be dumped raw ("[object Object]" / "[{...}]") into the
// toast. `humanDetail()` turns every error shape into one readable line.

const FIELD_LABELS = {
  name: '任务名称', subject: '科目', reward: '单次收益',
  weekly_min: '周最低次数', sort_weight: '排序权重',
  username: '用户名', password: '密码', old_password: '原密码',
  new_password: '新密码', date: '日期', task_id: '任务', completed: '完成状态',
};

// loc entries that describe *where* the error is, not *which* field failed.
const LOCATION_SEGMENTS = new Set(['body', 'query', 'path', 'header']);

/** ['body', 'reward'] -> '单次收益'; ['body'] -> '' (model-level error). */
function fieldLabel(loc) {
  if (!Array.isArray(loc)) return '';
  for (let i = loc.length - 1; i >= 0; i--) {
    const seg = loc[i];
    if (typeof seg !== 'string' || LOCATION_SEGMENTS.has(seg)) continue;
    return FIELD_LABELS[seg] || seg;
  }
  return '';
}

// Each renderer must cope with an empty label (model-level validation errors).
const ISSUE_RENDERERS = {
  missing: f => `${f || '参数'}为必填项`,
  string_too_short: f => `${f || '参数'}不能为空`,
  string_too_long: f => `${f || '参数'}超出最大长度`,
  string_pattern_mismatch: f => `${f || '参数'}格式不正确`,
  literal_error: f => `${f || '参数'}取值无效`,
  greater_than_equal: (f, i) => `${f || '参数'}不能小于 ${i.ctx?.ge ?? ''}`,
  less_than_equal: (f, i) => `${f || '参数'}不能大于 ${i.ctx?.le ?? ''}`,
  value_error: (f, i) => {
    const msg = String(i.msg || '').replace(/^Value error, /, '');
    return f ? `${f}：${msg}` : msg;
  },
};

export function humanDetail(detail) {
  if (detail == null || detail === '') return '';
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail) || detail.length === 0) return '请求参数不合法';
  const issue = detail[0];
  if (!issue || typeof issue !== 'object') return String(detail);
  const label = fieldLabel(issue.loc);
  const render = ISSUE_RENDERERS[issue.type];
  if (render) return render(label, issue);
  const msg = String(issue.msg || '请求参数不合法').replace(/^Value error, /, '');
  return label ? `${label}：${msg}` : msg;
}
