# fix-mimo.md — habits-tracker 架构缺陷与 Bug 鉴定 & 重构修复计划

> 版本：v4.1（commit `6331b41`）基线上的审计
> 日期：2026-09-30
> 方法：全量源码人工审阅（backend 1639 行 / frontend 1846 行）+ 动态复现脚本 + `pytest`(16 passed) + `ruff check`(clean) + 前后端 ISO 周算法 1500 天对拍
> 状态基线：`git status` clean，测试与 lint 全绿 —— **即：现有测试网无法捕获下列 P1/P2 缺陷**

---

## 0. 执行摘要

| 类别 | 数量 | 说明 |
|---|---|---|
| P1（数据口径错误 / 部署即错） | 2 | 已复现，直接影响收益结算与儿童打卡权限 |
| P2（可被触发的逻辑/健壮性缺陷） | 6 | 已复现或代码确证 |
| P3（潜伏/低危/回归） | 5 | 当前环境未爆，但条件一变即爆 |
| 架构缺陷 | 10 | 其中 A-01/A-02 直接孕育了 P1 bug |
| 测试缺口 | 6 类 | 权限矩阵、归档口径、时区、前端全部缺失 |

**一句话结论**：这个项目的"单点正确性"做得不错（周算法、并发锁、软删除都对），但**业务口径没有单一事实来源**——归档过滤、达标收益、周区间、科目常量各有 2~5 份实现，`/summary/weekly` 漏掉 `deleted_at IS NULL` 只是这类发散的第一次显形。修复重点不是打补丁，而是**先把口径收敛到一处，再补能抓住这类发散的测试**。

> **✅ 本文档的修复计划已于 2026-09-30 → 10-01 执行完毕（四轮验收，Phase 0/1/2/3 全 100%）。接手者请直接跳到 §7「交接」**：当前状态快照、未完成工作与优先级、复检命令、已知的坑，可从那里继续。

---

## 1. Bug 鉴定清单

### P1-01 `GET /summary/weekly` 未过滤已归档任务，与其余所有统计接口口径不一致

- **位置**：`backend/routers/summary.py:35`
  ```sql
  SELECT task_id, name, subject, reward, weekly_min FROM tasks   -- 缺 WHERE deleted_at IS NULL
  ```
  对比 `summary.py:165`（multi-week）、`records.py:19/128`（week）**都有**该过滤。
- **复现证据**（脚本见附录 A）：
  ```
  归档前: /summary/weekly 英语 = 1/7  reward 1.0
  归档后: /summary/weekly 英语 = 1/7  reward 1.0     ← 分母仍含归档任务（全量 15 项），且归档任务的完成仍计入收益
  归档后: /summary/multi-week = 0/14  reward 0.0     ← 同一周、同一数据，另一接口按 14 项（已排除归档）算
  归档后: /records/week task_progress = 14 项        ← 与 multi-week 一致，与 weekly 口径冲突
  ```
- **影响**：家长在"军令状"里归档一个任务后，"一周战果"页的达标率、总收益与"征途"页永久对不上，且收益虚高（归档任务的历史完成仍按 `reward × cnt` 计入，若归档任务恰好当周未达标则不计入 → 归档时机不同结果不同）。**这是钱的口径，不是显示问题。**
- **修复方向**：见 Phase 1「单一 active-tasks 查询源」——不是补一个 `WHERE`，而是让"任务清单"只有一种取法。
- **回归测试**：`test_summary_consistency.py::test_archived_task_consistent_across_endpoints`（同周同数据下 weekly / multi-week / records.week 三者 `total_tasks`、`tasks_met` 必须相等）。

### P1-02 Docker 容器未设时区 → 后端日期逻辑按 UTC 跑，与浏览器 Asia/Shanghai 错位 8 小时

- **位置**：`Dockerfile`（无 `ENV TZ`）、`docker-compose.yml`（无 `TZ`）；宿主机 `Timezone=Asia/Shanghai`，容器内默认 UTC。
- **受影响的裸日期调用**（全部使用 `date.today()` / `datetime.now()`）：
  | 文件:行 | 用途 | UTC 下的故障 |
  |---|---|---|
  | `backend/rules.py:49` | 儿童 7 天编辑窗口 | 每日 **00:00–08:00（北京时间）** 内，`today` 仍是昨天 → 儿童勾选"今天"返回 **403**；而前端 `app.js:283` 用浏览器本地时间判定"可编辑" → **按钮可点、后端拒绝** |
  | `backend/routers/summary.py:161` | 征途"当前周"起点 | 同上时段整个趋势表向前错一周 |
  | `backend/routers/summary.py:253` | `fulfilled_at` | 兑现时间少一天 |
  | `backend/database.py:27-28` | 周备份命名 `habits_YYYY_wWW` | 跨周当刻可能生成错周备份或漏备份 |
  | `backend/auth.py:61,77` | Session 过期判定 | 与 `COOKIE_MAX_AGE` 秒数语义混用（见 P3-09） |
- **影响**：README 推荐的正是 Docker 部署 → **默认部署形态下打卡权限每天有 8 小时窗口错乱**。
- **修复方向**：Phase 0 显式 `TZ=Asia/Shanghai`；Phase 2 引入可注入时钟，禁止裸 `date.today()`。
- **回归测试**：`test_clock.py`（注入假时钟，验证窗口边界）+ 容器内 `python -c "import time;print(time.tzname)"` 的 healthcheck 断言。

### P2-03 `week_completed_days` 把"零任务的空日"计为达标日

- **位置**：`backend/routers/records.py:121`
  ```python
  if day_records.completed_count >= day_records.total_count / 2:  # 0 >= 0 → True
  ```
- **复现**：归档全部任务后 `GET /records/week` → `week_completed_days = 7`（应为 0）。
- **影响**：字段当前前端未消费（见 D-05），但一旦接线就是错数据。
- **修复**：`total_count > 0 and completed*2 >= total_count`，并补 `total_count==0` 的单测。

### P2-04 `PUT /summary/fulfillment` 不校验周标识格式，垃圾数据可永久入库

- **位置**：`backend/routers/summary.py:241`（对比 `summary.py:30` 的 `weekly` 已正确调用 `weeks.parse_week_label`）
- **复现**：
  ```
  PUT /summary/fulfillment?week=garbage&fulfilled=true → 200 {'message': 'Updated'}
  GET /summary/fulfillment?weeks=garbage              → {'garbage': True}
  ```
- **影响**：`weekly_fulfillment.week` 有 UNIQUE 约束但无格式约束，脏键永久残留并参与前端勾选状态映射；绕过 `weeks.py` 收敛的入口。
- **修复**：`week = weeks.parse_week_label(week)` 只为校验（或加 `validate_week_label()`）；GET 端 `weeks` 列表长度上限。

### P2-05 登录限流字典无容量上限、可换用户名绕过、多进程失效

- **位置**：`backend/routers/auth_router.py:13-24`
- **复现**：
  ```
  10000 次不同 username 的失败尝试 → _login_attempts 累积 10000 条，仅同 key 再次命中才清理
  ```
- **三个问题**：
  1. **内存缓慢泄漏**：`defaultdict` 只在"该 key 再次被检查"时剪枝，孤儿 key 永久驻留 → 攻击者可 OOM。
  2. **可绕过**：key 是 `ip:username`，换用户名即重置 5 次预算 → 实质上无全局爆破预算。
  3. **多 worker 失效**：进程内状态，`uvicorn --workers N` 下限流形同虚设（当前单进程，属架构性隐患）。
- **修复**：Phase 3 换成有界 LRU + 按 IP 的总预算（如每 IP 每分钟 30 次），并注明"单进程假设"。

### P2-06 家长可对未来日期打卡，且前后端策略均未明确定义

- **位置**：`backend/rules.py:43-55`（`assert_editable_for_child` 只对 child 设上界 `today`，parent 完全无界）；`frontend/app.js:283`（parent 不排除 `d > today`）
- **复现**：`PUT /records date=today+10d` → **200**。
- **影响**：README 权限矩阵写的是"家长（任意历史日期）"，未来日期属未定义行为；家长在本周视图里能给周六周日提前打满卡，直接污染"一周战果"与收益结算。
- **修复**：明确策略 —— 推荐 `parent: [1970-01-01, today]`（禁止未来），并在 README 权限矩阵补一行；前端 `isEditable` 同步加 `d <= today`。

### P2-07 任务编辑的数字字段非法时静默丢弃（"假成功"）

- **位置**：`frontend/app.js:511-520`（`saveTask`）、`app.js:539-547`（`addTask`）
- **机理**：`parseFloat("")/v-model.number` 空值 → `NaN` → `JSON.stringify` 输出 `null` → `TaskUpdate.reward: Optional[float]` 把 `None` 当"未提供" → 不更新；而 `name/subject` 总是随包发送 → 接口 200 → Toast「保存成功」，**收益值实际没改**。
- **复现**：`PUT /tasks/en_word {"reward": null}` → `400 No fields to update`（单独发）；混在 `saveTask` 里则 200 假成功。
- **说明**：HISTORY.md v4.1 宣称已根治"假成功"，此为其残留形态。
- **修复**：前端 `Number.isFinite` 校验 + 后端对"显式提供但非法"的字段用 `Literal`/`Field(gt=0)` 拒绝（区分 `absent` 与 `null`，可改用 sentinel 或 `model_fields_set`）。

### P2-08 前端按 UTC 解析 `YYYY-MM-DD`，西半球时区会整日偏移（潜伏）

- **位置**：`frontend/app.js:306-310`（`new Date(d.date)` 后与本地 `today` 比对）、`app.js:477`（`formatTrendWeek` 的 `week_start`）、`app.js:306` `todayFooter` 匹配失败会静默显示 0/0。
- **机理**：ES 规范规定纯日期串按 **UTC 午夜** 解析 → 在 UTC-5 及以西会落到前一天；本机 Asia/Shanghai（UTC+8）恰好不触发。
- **修复**：统一 `parseDateLocal(s)`（按 `-` 切分构造），并纳入前端对拍测试。

### P3-09 时间戳格式三套并存，Session 清理用字符串比较

- **位置**：`backend/auth.py:41`（`datetime.now().isoformat()` → `2026-09-30T12:00:00.123456`）、`database.py` 表默认值 `CURRENT_TIMESTAMP`（`2026-09-30 12:00:00`，空格分隔）、`auth.py:77-83` `DELETE ... WHERE created_at < ?` 用 ISO 串比较。
- **现状**：`create_session` 恒显式传值，格式一致，故**当前恰好正确**；但只要有一条记录走表默认值（例如将来新增插入路径），字符串比较的分隔符/微秒差异就会静默漏删或误删。
- **修复**：Phase 2 统一存 UTC ISO8601（`datetime.now(timezone.utc).isoformat()`），`cleanup` 改用 `julianday()` 或 Python 侧解析，不依赖字典序。

### P3-10 Lifespan 后台任务取消未 await、维护节奏靠"每 24h 醒一次"

- **位置**：`backend/main.py:15-33`
  - `task.cancel()` 后未 `await` → 关闭时可能残留 "Task was destroyed but it is pending" 告警，异常被吞。
  - `periodic_maintenance` 先干活再 sleep 24h：若进程在周界附近长期运行，周备份依赖"每天恰好醒来一次"，**无对齐到自然日/周界的调度**。
  - `except Exception: print(...)` 吞掉所有维护错误，只打印。
- **修复**：`with contextlib.suppress(asyncio.CancelledError): await task`；改为计算"距下一个本地 03:00 的秒数"再 sleep；日志改 `logging`。

### P3-11 面向局域网的若干低危安全面

- `GET /docs` 与 `/openapi.json` 无鉴权公开（复现 200）→ API 面暴露。
- CORS `allow_origins=["*"]` + `allow_credentials=False`：当前安全（Cookie 不会被跨域携带），但属于"靠实现细节兜底"，应显式白名单或仅同源。
- `GET /summary/fulfillment?weeks=` 无长度上限 → `IN (...)` 无界拼接（参数化，非注入，但可构造大查询）。
- 缺 `X-Content-Type-Options`、`X-Frame-Options` 等基础响应头；Cookie 无 `secure`（HTTP 局域网可接受，需在 README 写明明文前提）。
- 默认口令 `parents`/`child` 写在 README 且种子逻辑 `database.py:159-172` 硬编码 → 应支持环境变量覆盖 + 首次登录强制改密。

### P3-12 同科目任务允许重名 → Vue `:key` 冲突

- **位置**：`frontend/index.html:241`（`:key="tp.name"`）；schema 对 `(subject, name)` 无唯一约束。
- **影响**：家长在同科目建两个同名任务（如两个"阅读100"，实际英语/语文已有同名但分属科目，科目内重名才触发）→ Vue 重复 key 告警 + 渲染错位。
- **修复**：`:key="tp.task_id"`（后端已返回 `task_id`），并加 `(subject, name)` 唯一性校验或明确允许。

### P3-13 上一次修复提交删除了 `daily_records` 索引 → 新旧库 schema 漂移

- **位置**：`commit 2a643d1` 删除 `backend/database.py` 中的 `CREATE INDEX IF NOT EXISTS idx_records_date_task ON daily_records(date, task_id)`。
- **证据**：
  - 现存 `data/habits.db`：`idx_records_date_task` **仍存在**（SQLite 不会因代码改动而删索引）。
  - 用当前代码全新 `init_db()`：索引**缺失**（只剩 sessions 的两个索引和各 UNIQUE 隐式索引）。
- **影响**：开发库与生产库 schema 不一致；任何"换机器 / 容器重建 / 换 DB 文件"的部署会静默丢失该索引，`/records/week`、`/records/range`、周聚合全部走 `date` 范围扫描。当前数据量小（约 15 任务 × 365 天）影响有限，但属**必须在 Phase 1 恢复的回归**。
- **修复**：以 `PRAGMA user_version = 3` 迁移重新 `CREATE INDEX IF NOT EXISTS`（幂等，对已有库无副作用）。

---

## 2. 架构缺陷清单

| ID | 缺陷 | 证据 | 后果 |
|---|---|---|---|
| **A-01** | **业务口径 2~5 份实现，无单一事实来源** | 科目常量散落 **7 处**：`config.py:17`、`database.py:107`(CHECK)、`app.js:6/233/258/535`、`index.html:225`；猫表情/进度条 2 份：`rules.py:8/27` vs `app.js:79/90`；ISO 周算法 2 份：`weeks.py` vs `app.js:34-60`；达标收益 2 份：`rules.calculate_reward`(无人调用) vs `summary.py:67,202` 内联 | **P1-01 就是这个缺陷的直接产物**；新增科目要改 7 处，漏一处即静默丢数据 |
| **A-02** | **Router 层直连 SQL，缺 service/repository 分层** | `summary.py` 255 行内嵌 4 段几乎相同的 `GROUP BY` 聚合；同一份"按周按任务计数"SQL 在 `records.py:133`、`summary.py:51`、`summary.py:96`、`summary.py:185` 出现 **4 次** | 归档过滤、周区间、达标判定等规则散落各处，改一处必漏一处 |
| **A-03** | **连接与查询模式碎片化，存在 N+1，且索引被误删（schema drift）** | `get_connection()`(直连) 与 `get_db()`(ctx) 两条路径并存；`records.py:116-123` 循环 7 天 = **8 个连接 / ≈15 条查询**；`summary.py:170-190` 26 周 = 26 条查询；**`2a643d1` 删除了 `idx_records_date_task`**：现存 `data/habits.db` 里该索引仍在（SQLite 不会随代码删除索引），但**任何全新 DB / 容器重建都不再有它** | HISTORY 宣称"消除 N+1"只覆盖 range/multi-week，`/records/week` 仍是重灾区；开发库与生产库 schema 已经不一致，属于**上一次修复引入的回归** |
| **A-04** | **配置全局可变且双份拷贝** | `database.py:9` `DB_PATH = config.DB_PATH` 在 import 期拍快照 → `tests/conftest.py:16-18` 必须同时 monkeypatch `config.DB_PATH` 和 `database.DB_PATH` | 任何新增读取点只要漏 patch，测试就会**写到真实 data/habits.db**（生产数据污染风险） |
| **A-05** | **迁移机制薄弱** | `database.py:200-212`：`user_version` 在 seed 之后读取、无事务包裹、无迁移记录表、每版一个手写 `if`；无 down/回滚 | 一旦出现需要改列型/回填数据的迁移，当前骨架撑不住 |
| **A-06** | **前端单文件巨石 + 手写日期算法 + 零测试** | `app.js` 637 行单组件、`index.html` 385 行内联模板；无 ESLint、无任何 JS 测试 | 本次对拍 1500 天**当前无漂移**，但全靠人肉维持；改一个视图要在 600 行里找状态 |
| **A-07** | **进程内状态假设，无法水平扩展** | 限流字典（`auth_router.py:13`）、后台任务单例（`main.py:31`） | 多 worker / 多实例部署时限流失效、备份重复执行 |
| **A-08** | **文档漂移（宣称与代码不符）** | ① HISTORY 称"添加 `escapeHtml()`"→ `app.js` 中 **0 处**（实际靠 Vue 文本插值免疫，属虚报）；② `project-conventions` skill 严重过时（端口 18765 / 单文件 index.html / `records` 表含 `user_id`，实际 15000 / 分文件 / `daily_records` 无 user_id）；③ README 权限矩阵未定义"未来日期"（P2-06） | 后续 agent/开发者按文档操作即踩坑 |
| **A-09** | **无 CI / pre-commit** | 仓库无 `.github/`、无 `.pre-commit-config.yaml`，ruff 与 pytest 仅手工执行 | 回归网形同虚设（本次 P1 缺陷全绿通过） |
| **A-10** | **死代码与未接线端点** | `rules.calculate_reward`（仅测试引用）、`rules.progress_bar`（零引用）、`GET /summary/week-earn`（前端零调用，实测 200 可用）、`models.UserCreate`、`WeekEarn.total_days`、`WeekRecords.week_completed_days`（前端不用且带 P2-03 bug） | "两套收益实现"是口径漂移温床；未接线端点 = 未被测试覆盖的攻击面 |

### 已验证**没有**问题的项（避免误修）

- 前后端 ISO 周算法 **1500 天对拍 0 差异**（含 2026-W53、跨年 W01）→ `weeks.py` 与 `app.js:getWeekStr/parseWeekStr` 当前等价，**不建议"顺手统一"，只需纳入对拍测试防漂移**。
- 权限矩阵实测：`child POST /tasks → 403`、`child PUT /fulfillment → 403`、`require_parent` 生效。
- 软删除 + FK：归档任务不可再写记录（404），历史记录保留。
- 并发：`busy_timeout=30000` + WAL，3 线程 ×10 写入 0 错误（既有测试覆盖）。
- XSS：全站无 `v-html`/`innerHTML`，Vue 文本插值天然转义。
- `ruff check` 全绿；`.pytest_cache` 等已被自身 `.gitignore` 自忽略，**无需修改根 `.gitignore`**。

---

## 3. 测试缺口（为什么 16/16 全绿却漏掉 P1）

| # | 缺失的测试 | 会抓住 |
|---|---|---|
| T-1 | 归档任务在 weekly / multi-week / records.week 三端口径一致性 | **P1-01** |
| T-2 | 注入时钟的编辑窗口边界（含"今天"、窗口首日、窗口外） | **P1-02** |
| T-3 | 权限矩阵表驱动测试（child × {POST/PUT/DELETE tasks, PUT fulfillment} → 403） | 权限回归 |
| T-4 | 未来日期策略（parent/child 双向断言） | **P2-06** |
| T-5 | `/summary/fulfillment` 非法 week → 400；限流 429 → **P2-04 / P2-05** |
| T-6 | 前端：ISO 周对拍脚本（node）+ 日期解析边界，纳入 CI | **A-06 / P2-08** |

现有 16 项测试全部针对"单接口内部"，**没有任何跨接口一致性断言**——这正是 P1-01 溜过去的原因。

---

## 4. 重构修复计划

### 总原则

1. **先收敛口径，再谈分层**：任何"补 WHERE 子句"式修复必须同时归拢到唯一实现，否则下一个接口还会漏。
2. **每个 Phase 独立可交付、可回滚**：Phase 0、2、3 **不改 schema**；仅 Phase 1 引入一个**幂等索引迁移**（`CREATE INDEX IF NOT EXISTS`，无数据变更）。
3. **每 Phase 的验收 = 新增回归测试变绿 + 既有 16 项仍绿 + ruff clean**。

---

### Phase 0 — 止血（0.5 天，P1 必修）

| 任务 | 文件 | 动作 |
|---|---|---|
| 0.1 归档口径 | `summary.py:35` | 暂加 `WHERE deleted_at IS NULL`（临时补丁位，Phase 1 收编） |
| 0.2 容器时区 | `Dockerfile` + `docker-compose.yml` | `ENV TZ=Asia/Shanghai`；compose 加 `TZ: Asia/Shanghai`；镜像装 `tzdata`（python:3.12-slim 需确认） |
| 0.3 空日达标 | `records.py:121` | `total_count > 0 and completed * 2 >= total_count` |
| 0.4 week 校验 | `summary.py:241` | `weeks.parse_week_label(week)` 校验 + fulfillment GET 长度上限（≤60） |
| 0.5 回归测试 | `tests/test_summary_consistency.py`、`tests/test_window_boundary.py` | 即 T-1/T-2 |
| 0.6 文档勘误 | `HISTORY.md`、README 权限矩阵 | 删除 `escapeHtml` 虚报；补"未来日期"策略说明 |

**验收**：`pytest` ≥ 20 项全绿；附录 A/B 脚本输出与修复后预期一致（weekly == multi-week == records.week；child 在 00:30 CST 可打卡）。

---

### Phase 1 — 口径归一（1–2 天，架构核心）

**目标**：`active-tasks` / `week-counts` / `reward` 各只有一份实现。

```
backend/
├── repo.py            # 新增：唯一 SQL 层
│   ├── list_active_tasks(conn, order=True) -> list[Row]      # 收编 records.py:19/70/128, summary.py:165, tasks.py:17
│   ├── week_completion_counts(conn, monday, sunday, task_ids) # 收编 4 处 GROUP BY
│   ├── day_records(conn, date)
│   └── upsert_record / batch（收编 records.py 的 UPSERT）
├── rules.py           # 唯一业务规则：calculate_reward 成为达标收益唯一实现
└── routers/*          # 只做 参数解析 → 调 repo/rules → 组装响应
```

| 任务 | 说明 |
|---|---|
| 1.1 | 新建 `repo.py`，把 4 处周聚合 SQL 与 5 处 active-tasks 查询收编 |
| 1.2 | `summary.weekly_summary`、`multi_week_summary`、`records.week` 全部改调 `repo.week_completion_counts`，**P1-01 由结构保证不会复发** |
| 1.3 | 收益结算改用 `rules.calculate_reward`，删除 `summary.py:67/202` 的内联 `reward * cnt` |
| 1.4 | 决策并执行：`GET /summary/week-earn` 接线到前端 **或** 删除（含 `WeekEarn` 模型）；删除 `rules.progress_bar`、`models.UserCreate`、`week_completed_days`（或补前端消费 + 修 P2-03） |
| 1.5 | 科目常量单一来源：后端 `config.SUBJECTS` 经 `/api/v1/config` 下发，前端 `app.js` 三处 + `index.html:225` 改读配置；DB CHECK 保留为最后防线并加注释说明二者关系 |
| 1.6 | `/records/week` 从 8 连接 15 查询 → **1 连接 3 查询**（任务清单 + 当周记录单查询 + 聚合） |
| 1.7 | 恢复被 `2a643d1` 删除的 `idx_records_date_task`（P3-13），以 `PRAGMA user_version = 3` 幂等迁移落地，避免新旧库继续漂移 |

**验收**：`test_summary_consistency` 通过；`/records/week` 查询数由 15 → 3（用计数断言或日志断言）；全量测试绿。

---

### Phase 2 — 时钟与时区收敛（1 天）

**目标**：消灭所有裸 `date.today()` / `datetime.now()`，让时间可测试。

| 任务 | 说明 |
|---|---|
| 2.1 | 新增 `backend/clock.py`：`today() -> date`、`now() -> datetime`、`settable` 测试钩子（默认 `Asia/Shanghai` 显式时区） |
| 2.2 | 替换 `rules.py:49`、`summary.py:161/253`、`database.py:27`、`auth.py:41/61/77` 全部调用点 |
| 2.3 | Session 时间统一 `datetime.now(timezone.utc).isoformat()`；`cleanup_expired_sessions` 改 `julianday(created_at) < julianday(?)`；写一次性兼容脚本处理旧格式（或直接全表重写 `created_at`） |
| 2.4 | 加防回归：ruff 自定义规则不可行则用 `grep` hook（pre-commit `regex` hook 禁止 `date.today()`/`datetime.now()` 出现在 `backend/` 除 `clock.py` 外） |
| 2.5 | 测试：`tests/test_clock.py` 覆盖窗口边界（今天/窗口首日/窗口外/跨 UTC 日界） |

**验收**：`grep -rn "date.today()\|datetime.now()" backend/ | grep -v clock.py` 为空；边界测试绿。

---

### Phase 3 — 安全与健壮性（1 天）

| 任务 | 对应 |
|---|---|
| 3.1 限流换有界实现（每 IP 全局预算 + per-key 滑动窗口 + 定期清扫 + 上限 10k 条），并在模块 docstring 声明"单进程假设" | P2-05 |
| 3.2 未来日期策略：`assert_editable_for_child` 改名 `assert_editable(role, target_date)`，parent/child 双向上界 `today`；前端 `app.js:283` 同步 `d <= today` | P2-06 |
| 3.3 数字字段校验：`TaskUpdate.reward: float = Field(gt=0, le=1000)`、`weekly_min: int = Field(ge=0, le=30)`，并用 `model_fields_set` 区分"未提供"与显式 null；前端 `Number.isFinite` 校验 + 明确错误 Toast | P2-07 |
| 3.4 `TaskBase.subject: Literal["英语","数学","语文"]`（与 `config.SUBJECTS` 生成） | A-01 |
| 3.5 关闭 `/docs`（生产 `docs_url=None`，dev 可开）；CORS 收敛为同源/白名单；补基础安全响应头中间件；fulfillment GET 长度上限 | P3-11 |
| 3.6 默认口令支持 `INITIAL_PARENT_PASSWORD` 环境变量覆盖，README 标注"部署后必改" | P3-11 |
| 3.7 `:key="tp.task_id"` | P3-12 |
| 3.8 lifespan：`await task` + 对齐到本地 03:00 的调度 + `logging` 替代 `print` | P3-10 |
| 3.9 补 T-3/T-4/T-5 权限与校验测试 | 测试缺口 |

**验收**：权限矩阵表驱动测试绿；`curl /docs` → 404；限流压测（1000 次不同用户名）内存稳定。

---

### Phase 4 — 结构与工程化（2–3 天，可延后）

| 任务 | 说明 |
|---|---|
| 4.1 配置单源 | 删除 `database.py:9` 拷贝，全项目 `config.DB_PATH` 动态读；`conftest.py` 只 patch 一处（A-04） |
| 4.2 迁移骨架 | `MIGRATIONS: list[Callable]` + 单事务执行 + `PRAGMA user_version` 在 seed 之前 + 每条迁移写日志（A-05） |
| 4.3 连接策略 | 用 FastAPI dependency 提供"每请求一个 conn"，替代函数内反复 `get_db()`；`/records/week` 单连接（A-03） |
| 4.4 前端拆分 | `app.js` → `lib/iso-week.js`、`lib/date.js`、`api.js` + `views/{Ambition,Daily,Weekly,Trend,Tasks}.js`；`index.html` 模板拆到各 view 文件（仍零构建，用 ESM 动态 import + `defineAsyncComponent`） |
| 4.5 前后端对拍 | `scripts/check-iso-week.mjs`：node 跑 `lib/iso-week.js` vs 后端 `weeks.py` 输出 1500 天 diff（复用附录 C 脚本），纳入 CI |
| 4.6 CI / pre-commit | GitHub Actions（或本机 pre-commit）：`ruff check` + `pytest` + 对拍脚本 + `grep` 时区 hook |
| 4.7 日期解析修复 | 前端统一 `parseDateLocal`（P2-08） |

**验收**：CI 一次跑通；前端拆分后各 view 文件 ≤ 150 行；对拍脚本 0 差异。

---

### Phase 5 — 可选增强（按需）

- 备份后 `PRAGMA quick_check` 校验，失败告警而非静默；备份命名加入 ISO 年（已是 `YYYY_wWW`，保留）。
- 结构化日志 + 请求 ID，替换全部 `print`。
- `/health` 增加 DB 可写性与 WAL 状态探针（现仅返回 `{"status":"ok"}`，**DB 挂了也报 ok**）。
- `data/backups` 保留策略改为按"ISO 周"而非字符串排序（当前 `sorted(key=name)` 在两位周号下正确，加入 53 周与跨年断言即可固化）。

---

## 5. 里程碑与回滚

| 阶段 | 工期 | schema 变更 | 回滚方式 |
|---|---|---|---|
| Phase 0 止血 | 0.5d | 无 | `git revert` 单 commit，无数据风险 |
| Phase 1 口径归一 | 1–2d | 仅新增索引（`user_version=3`，幂等） | 索引可 `DROP INDEX`；逻辑回滚 revert |
| Phase 2 时钟 | 1d | 无（session 时间格式变更需先 `cp data/habits.db` 快照） | 快照恢复 |
| Phase 3 安全 | 1d | 无 | revert |
| Phase 4 工程化 | 2–3d | 无 | 分多个小 PR，逐个 revert |

**动手前必做**：`cp data/habits.db data/backups/pre-refactor-$(date +%Y%m%d).db`（现有备份机制只在周界生成，不能替代手动快照）。

---

## 6. 修复验收记录（2026-09-30 复检）

> 复检方式：源码 diff 审阅（`git diff 6331b41`）+ 全量 `pytest` + `ruff check` + 附录 A 脚本重跑 + 新增针对性探针
> 第 1 轮（2026-09-30）：27 passed，判定 Phase 0 完成、1/2/3 大体完成、4 未开始
> 第 2 轮（2026-09-30，本文档 §6.6）：**35 passed** + 2225 例前后端对拍 + 596 条前端断言，§6.4 的 N-01~N-05 全部闭环，Phase 3.5/3.6/3.8 与 Phase 4 核心项补完
> 第 3 轮（2026-09-30，本文档 §6.7）：**39 passed**，按阶段拆 6 个 commit 并 push，Phase 5 首批落地，GitHub Actions 首跑通过
> 第 4 轮（2026-10-01，本文档 §6.4 N-06 / §6.8 / §6.9）：无头 UI 冒烟 22 项断言、视图层拆分（A-06）落地、CI 抓到并修复测试侧时区缺陷（N-06）、CSP 项拍板关闭
> 交付形态：**已提交并推送 `6331b41..b916fa0`（main，共 10 个 commit）**，DB 快照 `data/backups/pre-fix-20260930.db`；工作区干净，CI 3 跑全绿

### 6.1 Bug 逐条验收

| ID | 状态 | 修复落点 | 复检证据 |
|---|---|---|---|
| **P1-01** 归档口径 | ✅ **已修** | `summary.py:29` 改走 `repo.get_active_tasks`；收益改用 `rules.calculate_reward` | 三端复检：weekly `total_tasks=6` == multi-week `6` == records/week `6`；`grep "reward \* cnt"` 零命中 |
| **P1-02** 容器时区 | ✅ **已修** | 新增 `backend/clock.py`（固定 `Asia/Shanghai`）+ Dockerfile `apt tzdata` + `ENV TZ` + compose `TZ` | `grep "date.today()\|datetime.now()" backend/` **零命中**；`test_clock_mock_and_shanghai_timezone`（北京 00:30 → 200）通过 |
| **P2-03** 空日达标 | ✅ 已修 | `records.py:128` 加 `total_count > 0` | 全归档 → `week_completed_days = 0`（原 7） |
| **P2-04** fulfillment 校验 | ✅ 已修 | `summary.py:174` `parse_week_label` + `:156` GET ≤60 | `week=garbage` → **400**（原 200） |
| **P2-05** 限流 | ✅ 已修 | `BoundedRateLimiter`：IP 30/分 + IP:User 5/分 + `max_keys=1000` + 过期剪枝 | 单测验证预算与容量上限；`_login_attempts` defaultdict 已删除 |
| **P2-06** 未来日期 | ✅ 已修 | `rules.py:46-48` parent → 400；`app.js:283` `(parent‖窗口) && d <= today` | parent +10d → **400**（原 200）；child → 403；双角色测试 ✓ |
| **P2-07** 数字假成功 | ✅ 已修 | 前端 `Number.isFinite`/`isInteger` 拦截 + 后端 `reject_explicit_nulls` + `Field(ge=…)` | `{"reward": null}` → **422**（原静默 200）；负数、非法科目均 422 |
| **P2-08** UTC 解析 | ✅ **已修（第 2 轮）** | 新增 `frontend/lib/dates.js` 的 `parseDateLocal()`，替换 `app.js` 两处 `new Date(串)` | `node scripts/frontend_unit.mjs`：`formatDate(parseDateLocal('2026-03-05')) == '2026-03-05'` 且解析结果落在本地 00:00 |
| **P3-09** 时间戳格式 | ✅ **已修（第 2 轮）** | `cleanup_expired_sessions` 改用 `julianday(created_at) < julianday(?)` | 实测 `julianday()` 对 `+00:00`、`T` 分隔、空格分隔、naive 四种格式均解析正确，按时间点而非文本比较 |
| **P3-10** 后台任务 | ✅ **已修（第 2 轮）** | `main.py` 改为对齐 `MAINTENANCE_HOUR`（默认 03:00 Asia/Shanghai）计算下次睡眠；6 处 `print` 全部改 `logging`（`habits` / `habits.auth` / `habits.database` logger） | `scripts/check_bare_dates.sh` 通过；`seconds_until_next_maintenance()` 单点可测 |
| **P3-11** 安全面 | ✅ **已修（第 2 轮）** | `docs_url/redoc_url/openapi_url` 由 `ENABLE_DOCS` 门控；CORS 中间件仅在 `CORS_ORIGINS` 非空时挂载；新增安全响应头 + CSP 中间件；`INITIAL_*_PASSWORD` 走环境变量 | `test_api_docs_disabled_by_default`、`test_security_headers_on_every_response`、`test_cors_is_disabled_by_default`、`test_seed_credentials_read_from_config` 全部通过 |
| **P3-12** Vue key | ✅ 已修 | `index.html:241` `:key="tp.task_id"` | grep 确认 |
| **P3-13** 索引漂移 | ✅ 已修 | `database.py:152` 无条件 `CREATE INDEX IF NOT EXISTS` + `:213-216` `user_version=3` 迁移 | 幂等，对现存库无副作用 |

### 6.2 阶段计划验收

| Phase | 完成度 | 已完成 | 未完成 |
|---|---|---|---|
| **0 止血** | **100%** | 0.1–0.6 全做（含 HISTORY `escapeHtml` 勘误、README 未来日期策略） | — |
| **1 口径归一** | **100%** | `repo.py` 收编 5 处 active-tasks + 4 处周聚合 + **batch 存在性校验（`repo.get_existing_active_task_ids`）**；`/records/week` **1 连接 3 查询**（有断言测试 `test_records_week_query_efficiency`）；死代码清零；索引恢复；**1.5 科目已由 `/config` 驱动**（`subjectList` / `weeklySubjects` computed，5 处硬编码 + 趋势表头表体 + 科目下拉全部改读）；**multi-week 批量化（§6.7）**：整段范围 1 条查询替代每周 1 条 | — |
| **2 时钟收敛** | **100%** | `clock.py` + 全项目裸日期调用零残留 + mock 注入点；**`scripts/check_bare_dates.sh` 作为 pre-commit/CI hook**；**2.3 `cleanup` 改 `julianday()` 比较** | — |
| **3 安全健壮** | **100%** | 3.1 ✅ 3.2 ✅ 3.3 ✅ 3.4 ✅ 3.7 ✅ **3.5 ✅（docs 门控 / CORS 收敛 / 安全头 + CSP）** **3.6 ✅（`INITIAL_*_PASSWORD` 环境变量）** **3.8 ✅（对齐 03:00 + `logging`）** **3.9 ✅（`'unsafe-eval'` 维持——第 4 轮拍板关闭，§6.8.3）** | —（`/health` DB 可写探针已随 Phase 5 完成） |
| **4 工程化** | **~90%** | **A-04 `DB_PATH` 单源**（`database.py` 动态读 `config.DB_PATH`，conftest 只 patch 一处，`test_seed_credentials_read_from_config` 验证）；**迁移字典 `MIGRATIONS` + 建表→迁移→播种顺序**；**对拍脚本进仓库并接 CI**（`scripts/parity_*` 2225 例）；**`parseDateLocal`**；**pre-commit + GitHub Actions**；前端纯函数拆到 `frontend/lib/`（4 模块）；**A-06 / 4.4 视图层拆分 ✅（第 4 轮）**——`app.js` 604 → 230 行、`frontend/views/` 5 模块、护栏改造 + 22 项 UI 冒烟门禁（§6.8.2） | **4.3 连接策略**（每请求一个 conn 的 dependency 化，A-03 尾巴）——热点 N+1 已修（`/records/week` 单连接 3 查询、multi-week 单查询），属结构性优化，**按需** |
| **5 可选** | **~60%** | **3.10 `/health` DB 写探针 ✅**（`BEGIN IMMEDIATE`，异常 503）、**3.11 multi-week 批量化 ✅**（详见 §6.7）；CSP 去 `'unsafe-eval'` **已拍板关闭（§6.8.3）** | 仍按需未做：备份后 `PRAGMA quick_check`、结构化日志 + 请求 ID、备份轮转补 53 周/跨年断言 |

### 6.3 测试网对照（16 → 35 项，+19；第 3 轮后 **16 → 39 项，+23**）

| 计划项 | 状态 | 说明 |
|---|---|---|
| T-1 归档口径三端一致 | ✅ | `test_archived_task_consistent_across_endpoints` |
| T-2 注入时钟窗口边界 | ✅ | `test_clock_mock_and_shanghai_timezone`；**N-04 已补**：conftest 增加 autouse `_reset_global_state`，每个用例前后自动 `set_mock_time(None)` + 清空限速器 |
| T-3 权限矩阵表驱动 | ✅ | 第 2 轮补齐 `child × {POST/PUT/DELETE /tasks}` 403 + `child GET /tasks` 200（`test_child_cannot_manage_tasks`） |
| T-4 未来日期策略 | ✅ | parent 400 + child 403 双断言 |
| T-5 week 校验 + 限流 | ✅ | week/60 上限 ✅；**登录端到端 429**（`test_login_rate_limit_returns_429`，conftest autouse 复位限速器防串测） |
| T-6 前端对拍 + 日期解析 | ✅ | `scripts/parity_check.sh`（2225 例：周标签/周界/解析/表情）+ `scripts/frontend_unit.mjs`（596 断言，含 `parseDateLocal` 与 `humanDetail`），均已接 CI |

### 6.4 本轮复检新发现（N-01~N-05 第 2 轮闭环；N-06 第 4 轮发现并闭环）

| ID | 级别 | 问题 | 证据 | 状态 |
|---|---|---|---|---|
| **N-01** | P2 | **把"静默假成功"改成了"看不懂的失败"**：后端 422 的 `detail` 是对象数组，前端 `api()` 直接 `showToast(err.detail)` → Toast 渲染 `[{'type': 'value_error', …}]` | 实测 422 detail 为 `[{type,loc,msg,input,ctx}]`；`app.js` 未做归一化 | ✅ 新建 `frontend/lib/errors.js`（`humanDetail`，字段中文标签 + 类型化渲染），429 单独分支；`frontend_unit.mjs` 8 例覆盖 |
| **N-02** | P2 | `TaskBase` 给 `reward=0.0`、`weekly_min=1` 加了默认值 → `TaskCreate` 必填变可选，`POST /tasks` 不带 reward 返回 **200**、静默建出 0 收益任务 | 复检 `POST {"task_id","subject","name"}` → 200 | ✅ `TaskCreate` 显式覆写为必填（`TaskUpdate` 仍全可选），`test_task_create_requires_reward_and_weekly_min` 断言缺字段与显式 null 均 422 |
| **N-03** | P2 | **文档漂移复发（A-08）**：README 结构树缺 `repo.py`/`clock.py`，`rules.py` 描述仍写"进度条"（已删），测试清单缺 3 个新文件；HISTORY 无本轮修复条目；`project-conventions` skill 未更新 | `grep -n "repo.py\|clock.py" README.md` 无命中 | ✅ README 结构树/测试清单/环境变量表/安全默认值重写，HISTORY 新增 **v4.2** 条目，`~/.claude/skills/project-conventions/SKILL.md` 已重写为"硬约定 + 提交前检查"速查（删掉与 README 重复且已过时的结构树/表名） |
| **N-04** | P3 | `clock.set_mock_time` 是模块级全局，靠各测试 `try/finally` 清理 → 一旦某个用例漏写，后续所有用例跑在假时间上（静默污染） | `tests/test_clock_and_security.py:12-24` | ✅ conftest 增加 autouse `_reset_global_state`，覆盖 mock 时钟与限速器两类全局状态 |
| **N-05** | P3 | `assert_editable_for_child` 现在同时约束 parent 的未来日期，名不副实 | `rules.py:34` | ✅ 改名 `assert_editable`，docstring 明确三档规则；`records.py` 2 处调用与 `test_rules.py` 同步 |
| **N-06** | P2 | **测试读宿主机日期而非 app 时钟**：`tests/*` 用 `date.today()`（宿主 TZ）与业务侧 `clock.today()`（Asia/Shanghai）比日期，两者在 **16:00–24:00 UTC 日历分叉** → **CI 每天有 8 小时必挂、本地（上海）永远绿**；裸时钟守护只扫 `backend/`，管不到 `tests/` | `TZ=UTC pytest tests/test_rules.py` → 1 failed；CI run `36745393050` 同样失败，而同一时刻本地 39 全绿 | ✅ 第 4 轮（`daee234`）：13 处改 `clock.today()`；`test_child_editable_window_rule` **钉死 mock 时钟**（任何 TZ 下确定）；`check_bare_dates.sh` 扩到 `tests/`（`datetime.now()` 测耗时仍允许），变异验证注入即 exit 1；`TZ=UTC` 全量 39 passed |

### 6.5 第 1 轮结论与下一步优先级（已执行完毕，保留作对照）

**判定（第 1 轮）：Phase 0 完成、Phase 1/2/3 大体完成（85%/75%/70%），Phase 4 未开始。核心 P1/P2 已全部闭环且有回归网，可以交付。**

原建议的下一批 7 项，**全部在第 2 轮完成**：

| # | 项目 | 状态 | 落点 |
|---|---|---|---|
| 1 | N-01 422 detail 归一化 | ✅ | `frontend/lib/errors.js` + `api()` 429 分支 |
| 2 | N-02 `TaskCreate` 必填 | ✅ | `backend/models.py` |
| 3 | Phase 3.5 + 3.6 安全面 | ✅ | `backend/main.py`、`backend/config.py` |
| 4 | P2-08 + T-6 `parseDateLocal` + 对拍脚本 | ✅ | `frontend/lib/dates.js`、`scripts/` |
| 5 | Phase 1.5 科目改读 config | ✅ | `frontend/app.js`、`frontend/index.html` |
| 6 | Phase 4 核心（`DB_PATH` 单源 + pre-commit/CI） | ✅ | `backend/database.py`、`tests/conftest.py`、`.pre-commit-config.yaml`、`.github/workflows/ci.yml` |
| 7 | N-03 文档同步 | ✅ | `README.md`、`HISTORY.md` v4.2、`project-conventions` skill（仓库外） |

**流程提醒（已执行）**：全部改动**尚未提交**——该状态已结束，实际按 6 个 commit 分批提交（`fix` ×2 → `test` → `docs` → `feat`）并 push（`6331b41..4903066`）；提交前已做 DB 快照 `data/backups/pre-fix-20260930.db`。原始建议的 commit 拆分粒度与实际略有出入，见 §6.7。

### 6.6 第 2 轮补完记录（2026-09-30）

**验收命令与结果**（全部在仓库根目录执行）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `.venv/bin/python -m pytest -q` | **35 passed**（27 → 35，新增 `tests/test_hardening.py` 8 项） |
| 代码风格 | `.venv/bin/ruff check .` | All checks passed |
| 裸时钟守护 | `./scripts/check_bare_dates.sh` | 通过（`backend/` 内 `date.today()` / `datetime.now()` 零命中） |
| 前后端对拍 | `./scripts/parity_check.sh` | **2225 cases match**（1500 天周标签 + 110 例周解析 + 153 例表情分级） |
| 前端检查 | `./scripts/check_frontend.sh` | **596 assertions** + 5 个模块语法检查 + **163 条模板绑定检查**通过 |
| CI / 钩子 | `.github/workflows/ci.yml`、`.pre-commit-config.yaml` | YAML 校验通过（本地未实际运行 pre-commit，需先安装）→ **第 3 轮已在 GitHub Actions 实跑通过**（§6.7） |
| 运行时冒烟 | `uvicorn` 起在 `127.0.0.1:15999`（`DATA_DIR=/tmp/opencode/smoke-data`，与生产 15000 容器隔离）+ curl 全链路 | `/` 与 `/app/**`（含 `lib/*.js`）全 200；登录 200；`/config` 返回 `subjects`；缺 `reward` 的 `POST /tasks` → **422**；未来日期 → **400**；`week=garbage` → **400**；`/docs`、`/openapi.json` → **404**；响应头含 nosniff / DENY / CSP；生产容器 15000 未受影响 |

> **浏览器冒烟未做**：`browser` 工具报 `No desktop browser is connected to this session`。替代验证 = 上表 curl 全链路 + `scripts/check_template_bindings.mjs`（163 条模板表达式对 `setup()` 返回值做静态交叉检查，可捕获 `v-for="sub in weeklySubject"` 这类只在运行时才暴露的笔误；已用故意注入的 typo 验证其会非零退出）。 **→ 已被取代**：第 4 轮落地 `scripts/ui_smoke.py` 无头浏览器冒烟（22 项断言，§6.8.1）。

**遗留项（按优先级）**：

1. ~~**未提交**~~ ✅ **已完成（第 3 轮）**：按 §6.5 拆成 6 个 commit（`fix` ×2 → `feat` → `test` → `docs`，每个 commit 在独立 worktree 中跑过 pytest + ruff），DB 快照 `data/backups/pre-fix-20260930.db`，已 push `6331b41..4903066`。
2. ~~**A-06 / Phase 4.4 前端视图层拆分**~~ ✅ **已完成（§6.8.2）**：`app.js` 604 → 230 行，视图状态迁至 `frontend/views/`（5 模块），护栏先改造并经 2 次变异验证，暴露面守恒 50 绑定，无头 UI 冒烟 22/22 通过。剩余可选项：`daily.js`（215 行）内的浮层可再抽 `daily-picker.js`。
3. ~~**CSP 去除 `'unsafe-eval'`**~~ ✅ **已拍板关闭（won't fix，2026-10-01，§6.8.3）**：与零构建定位冲突且增量防护很薄，唯一重开前提 = 暴露公网。~~`/health` DB 探针、multi-week 批量化~~ → 已在 §6.7 完成。
4. ~~**CI 首次验证**~~ ✅ **已完成（第 3 轮）**：run [`36739261620`](https://github.com/tayhe/habits-tracker/actions/runs/36739261620) **41s 全绿**，ruff / pytest(39) / 裸时钟守护 / 前端单测与语法 / 对拍 2225 六项均通过；两条 annotation 仅为外部弃用提示（Node 20、ubuntu-latest 迁移）。
5. ~~**浏览器冒烟**~~ ✅ **已完成（2026-10-01）**：改为 Playwright 无头方案（桌面端始终未连接），`./scripts/ui_smoke.sh` 22 项断言全过，覆盖雄心/每日/战果/征途/军令状五视图 + `subjectList` 接线 + console/HTTP 全零，并经变异验证有效。详见 §6.8.1。

### 6.7 Phase 5 增量（同日追加）

| 项 | 结果 | 证据 |
|---|---|---|
| **`/health` 真实就绪探针** | `SELECT 1` + `BEGIN IMMEDIATE` 写探针（`busy_timeout=3s`，卡在 compose 的 5s 超时内），返回 `db.journal_mode` / `db.schema_version`；数据库不可用 → **503**，不再是"DB 挂了也报 ok" | `test_health_reports_database_state`、`test_health_returns_503_when_database_unavailable` |
| **`/summary/multi-week` 批量化** | 整段范围**一条** SQL + Python 按 `weeks.iso_week_label` 分桶；26 周由 26 次查询降到 1 次。`get_completion_counts` 改为对同一实现的聚合，weekly / multi-week / records 三处调用共用一个过滤条件 | `test_multi_week_matches_weekly_endpoint`（与 `/summary/weekly` 逐项对齐，含防空断言）、`test_multi_week_issues_single_records_query`（weeks=8 断言恰好 1 条 `daily_records` SELECT） |
| **测试** | pytest **39 passed**（35 → 39）；ruff / 裸时钟 / 对拍 2225 / 前端 596+163 全绿 | — |
| **提交与推送** | 按阶段拆 **6 个 commit**：`fix`(repo/clock/SQL 单源) → `fix`(docs 门控/CORS/安全头) → `fix`(前端错误归一/本地解析/科目 config) → `test`(+CI/pre-commit) → `docs` → `feat`(本项)；每个中间 commit 均在独立 worktree 中验证 pytest + ruff 通过后再提交 | `git log 6331b41..4903066`，工作区 clean |
| **CI 首跑** | GitHub Actions `checks` **41s 全绿**：ruff、pytest(39)、裸时钟守护、前端单测与语法、前后端对拍 2225 六项全通过 | run [`36739261620`](https://github.com/tayhe/habits-tracker/actions/runs/36739261620) |

**三项遗留全部闭环**（评估与决策见 **§6.8**）：① 浏览器冒烟 → ✅ Playwright 无头 22 项断言（§6.8.1）② 视图层拆分 → ✅ `app.js` 604 → 230 行、暴露面守恒（§6.8.2）③ CSP 去 `'unsafe-eval'` → ✅ **拍板关闭（won't fix）**（§6.8.3）。**下一步建议见 §6.9。**

### 6.8 三项遗留的评估与决策（第 3 轮后续）

| # | 项 | 决策 | 结论所在 |
|---|---|---|---|
| 5 | 浏览器四视图冒烟 | ✅ **已完成**：`scripts/ui_smoke.sh` + `ui_smoke.py`（Playwright 无头 Chromium），22 项断言 + 变异验证 | §6.8.1 |
| 2 | 前端视图层拆分（A-06 / Phase 4.4） | ✅ **已完成**：以 §6.8.1 为门禁执行，暴露面守恒（50 绑定）+ 22 项 UI 冒烟全绿 | §6.8.2 |
| 3 | CSP 去除 `'unsafe-eval'` | ✅ **已拍板关闭（won't fix，2026-10-01）** | §6.8.3 |

#### 6.8.1 浏览器冒烟 → Playwright 无头脚本（已选定）

**为什么现有手段不够**：本轮有两处纯 UI 行为改动（趋势表列头/表体、任务管理科目下拉改由 `/config` 的 `subjectList` 驱动），三种验证各差一口气。

| 手段 | 能证明 | 证明不了 |
|---|---|---|
| curl 全链路 | `/config` 返回 `subjects` | 浏览器是否拿它去渲染 |
| `check_template_bindings.mjs`（87 绑定 × 163 表达式） | 模板标识符在 `setup()` 返回面**存在** | 取值正确性、最终 DOM |
| pytest 39 项 | 后端契约 | 以上两项 |

**方案**：`uv add --dev playwright` + Chromium（无头），新增 `scripts/ui_smoke.py` + `scripts/ui_smoke.sh`（脚本自带隔离实例：`DATA_DIR=/tmp/opencode/ui-smoke-data`、`127.0.0.1:15999`，与生产 15000 容器隔离）。断言面：

1. UI 登录 → `#app` 可见、头部用户名正确；
2. 五个视图逐个切换（喵的雄心/每日捕猎/一周战果/征途/军令状），各自容器**非空渲染**（捕获"静默空白"这一最典型的回归形态）；
3. `#trendView thead` 学科列 == `/api/v1/config` 的 `subjects`，`tbody` 行数 ≥ 2（需先经 API 播种近两周记录）；
4. `#taskMgmtView` 科目下拉 options == `subjects`；
5. 全程 **console error / pageerror / ≥400 响应均为 0**；
6. 每视图截图留档。

**价值**：一次性解开"零前端测试网"这个根约束，因此它同时是 §6.8.2 的前置护栏。

**执行结果（2026-10-01）**：

| 项 | 结果 |
|---|---|
| 依赖 | `uv add --dev playwright`（1.63.0）+ `uv run playwright install chromium`（Headless Shell **153.0.8010.12**，aarch64 免额外系统依赖直接启动） |
| 用例 | `./scripts/ui_smoke.sh`：**22 项断言全过，exit 0**；隔离实例（`127.0.0.1:15999` + `/tmp/opencode/ui-smoke-data`，每次 wipe 重建、拒绝接管已占用端口）；播种 **33 条打卡**（11 天 × 3 任务），趋势表命中 **W39=2.8 / W40=1.2** 两周收益 |
| 接线 | 征途表头学科列 `['英语','数学','语文']` == `/config.subjects`；军令状 **15 行**科目下拉逐行 == `subjectList`；征途 8 行数据、2 周有收益 |
| 静默性守卫 | 五视图各断言 `innerText ≥ 20 字符`（拦截"静默空白"），且 console error / pageerror / HTTP≥400 / 请求失败**全为 0**（唯一白名单 = `GET /auth/me` 登录前 401，属会话恢复探测的设计行为） |
| 截图 | `/tmp/opencode/ui-smoke-shots/{1..5}-<视图名>.png` |
| **变异验证** | 把 `subjectList` 取值改成 `config.value.subjectz`——这是"只有浏览器能发现"的真错误 → `app.js:184` 抛 `TypeError: Cannot read properties of undefined (reading 'map')`，`#app` 永不出现 → 冒烟 **exit 1**（`UI 登录失败` + `console error = 1` 并打印堆栈）。pytest / `check_template_bindings.mjs`（该标识符仍是合法返回绑定）/ curl 在同一变异下**均仍为绿**。还原后复跑恢复 22 项全绿 |

**局限**：① 仅桌面视口 1440×960，未覆盖移动端与暗色模式；② 行为级断言，不做像素/视觉回归；③ 未进 CI（runner 需额外 `playwright install chromium`，可作后续可选 job）。

#### 6.8.2 前端视图层拆分（A-06 / Phase 4.4）—— 在 §6.8.1 完成后进行

**现状**：`app.js` **604 行**、单个 `createApp({setup()})`，5 个视图仅靠注释分块（Ambition `:170` / Daily `:198` / Weekly `:378` / Trend `:407` / TaskMgmt `:455`），`:542` 一次性返回 **87 个绑定**；模板 379 行、55 个指令，**不改模板**。目标形态：各视图状态抽成 `frontend/views/*.js` 工厂（`({ctx}) => ({...bindings})`），`app.js` 只做拼装；纯函数已在 `frontend/lib/`。

**性质**：不修任何 bug，纯可维护性。

**隐藏工作量（易被忽略）**：`check_template_bindings.mjs` 是**用正则定位单个 `return {…}` 块**的；拆成 5 个工厂后它会失效或误报——**必须先改造该脚本**，否则等于先拆护栏。约占 0.5h。

**最大风险**：漏一个返回绑定 → 模板变量 `undefined` → 界面**静默空白而非报错**。因此硬依赖 §6.8.1 的可执行验证——**拆完全绿不等于界面没白**。

**工作量**：视图改造 1–2h + 检查脚本改造 0.5h + 验证 0.5h ≈ 半天。

**执行约束**（用户已确认的排期）：① 必须在 §6.8.1 落地后进行；② 一次拆完 5 个视图，不半拆（半拆比不拆更乱）；③ 仅在确实有持续改视图的需求时才值得做，否则是"为整洁而拆"。

**执行记录（2026-09-30 → 10-01，已完成）**：

| 项 | 结果 |
|---|---|
| **护栏先行改造** | `check_template_bindings.mjs` 由"正则定位单个 `return {`"改为**多来源收集**（`app.js` setup 的 return + 每个 `views/*.js` 的 `bindings: {…}`，花括号配对并跳过字符串与注释），顺带修掉"注释尾词被当成 binding"的虚高计数（87 → 实际 50）；新增对 `name: value` 写法的定位提示。**变异验证 ×2**：删掉 `dailyDays,` → exit 1 并点名；改成 `dailyDays: weekData,` → exit 1 并打印"改用简写"的 hint |
| **拆分结果** | `app.js` **604 → 230 行**（只剩全局状态、api/鉴权/toast、视图装配与 `switchView`）；新增 `frontend/views/`：`ambition` 42 / `weekly` 46 / `trend` 69 / `tasks` 78 / `daily` **215** 行。契约统一为 `{ load, bindings, docClick? }`，`switchView` 按视图名派发 `load`，`setup()` 返回 `...viewBindings` |
| **暴露面守恒** | 拆分前后绑定数**均为 50**（护栏报数），模板 163 条表达式 0 缺失——静态层面证明没有丢绑定 |
| **门禁（§6.8.1）** | 无头 UI 冒烟 **22/22 通过**：五视图非空渲染、趋势表头/15 行下拉 == `subjectList`、播种收益落表（W39=2.8 / W40=1.2）、console/pageerror/HTTP 全零；另 `check_frontend.sh` 扩到 `views/*.js` 的 `node --check`，pytest 39（含 `TZ=UTC` 复跑）、对拍 2225 均绿 |
| **偏离计划** | `daily.js` **215 行 > 150 行**目标：它还含"补录任务"浮层，而浮层与 `weekData` / `loadWeekData` 强耦合，抽出需注入两个内部引用、纯增一层间接，故本轮不抽；如需可后续出 `views/daily-picker.js`（约 −90 行） |

#### 6.8.3 CSP 去除 `'unsafe-eval'`（已拍板：关闭 / won't fix）

**事实**（已核实）：`frontend/vendor/vue.esm-browser.prod.js` 是 **Vue 3.5.42 完整版（含编译器，172KB）**，全文件唯一的执行汇点为 `s = Function("Vue", l)(oC)`，用于把 `index.html` 的 in-DOM 模板编译成渲染函数——**移除 `'unsafe-eval'` 会让四个视图全部编译失败、页面空白**。这不是配置疏忽，而是「零构建 + 模板写在 HTML 里」这个架构选择的必然代价。

**收益评估（建议不做的核心理由）**：局域网威胁模型下，当前 CSP 已含 `default-src 'self'`、`object-src 'none'`、`frame-ancestors 'none'`，且**没有 `unsafe-inline'`**——注入的内联 `<script>` 与 `onerror=` 事件处理器**均已被挡住**；`unsafe-eval` 只额外影响"攻击者能拿到 `eval`/`Function` 汇点"的场景，而应用代码 `eval(` / `new Function` **0 命中**、无此类汇点。即：换来的是一层很薄的增量防护。

**代价**：必须预编译模板 → 引入代码生成步骤 → **打破 README 的「零构建」核心定位**，并新增经典脚枪：改了 `index.html` 忘记重新生成 → 界面悄悄不更新（与本项目反复中招的"漂移"类 bug 同源），还得再加"CI 重新生成并 diff"的守护去堵。

| 方案 | 可行性 | 代价 |
|---|---|---|
| 代码生成（`@vue/compiler-dom`）+ CI diff 守护 | ✅ 技术可行 | 放弃零构建 + 新增漂移面 |
| 手写 render 函数 | ✅ | DX 崩溃，不可接受 |
| **保持现状并在文档记录理由** | ✅ | **零** |

**建议结论**：**关闭该项（won't fix）**。唯一能改变结论的前提 = 应用暴露到公网或面向不可信用户；届时再执行方案一。

**拍板记录（2026-10-01，用户决定）**：**关闭**，理由与三方案对比如上存档。**重开条件** = 应用暴露到公网或面向不可信用户 → 届时执行方案一（预编译 + CI diff 守护）。`backend/main.py` 的 CSP 保持不变，其注释已记录该取舍。

---

### 6.9 下一步建议（第 4 轮收尾，2026-10-01）

**已闭环**：§1 全部 13 个 bug（2 P1 / 6 P2 / 5 P3）；§2 十项架构缺陷中的 A-01、A-02、A-03（主体）、A-04、A-05、**A-06（第 4 轮）**、A-08、A-09、A-10；§3 六类测试缺口（pytest **16 → 39**，另 2225 例对拍 + 596 前端断言 + 163 静态绑定 + 22 项 UI 冒烟，全部接 CI）；阶段上 Phase 0/1/2/3 **100%**、Phase 4 **~90%**、Phase 5 **~60%**。

| 优先级 | 项 | 判断 |
|---|---|---|
| **建议做** | CI 加 UI 冒烟 job（runner 上 `playwright install chromium`） | 冒烟目前只有本地手动跑，是最新也最脆的一层防线；进 CI 才算长期门禁。约 20 行 yml，CI 41s → ~90s |
| 按需 | Phase 4.3 连接策略（每请求一个 conn 的 dependency 化，A-03 尾巴） | 热点 N+1 已修（week 单连接、multi-week 单查询），属结构性优化，无 bug 驱动 |
| 按需 | Phase 5 剩余：备份 `PRAGMA quick_check`、结构化日志 + 请求 ID、备份轮转 53 周/跨年断言 | 单机局域网部署下收益低，均为健壮性锦上添花 |
| 按需 | A-07 进程内状态（限流字典 / 后台任务单例） | 仅在真要多 worker / 多实例时才有意义，**条件触发** |
| 可选 | 抽出 `views/daily-picker.js`（`daily.js` 215 → ~125 行） | 纯整洁项，有 22 项冒烟做门禁，风险低 |

**建议顺序**：① 先做 CI 冒烟 job，把最新、也是最脆的一层防线固化 → ② 其余全部标注"条件触发"不排期，等真实需求（公网暴露 / 多实例 / 持续改视图）再启动 → ③ 本轮文档同步后，交付即完全闭环。

---

## 7. 交接（Handoff）— 供接手 Agent

> 写于 **2026-10-01**，对应 commit `eef45e3`。**接手第一步 = 跑 §7.4 的复检命令确认基线**，然后从 §7.3 由上往下挑活。

### 7.1 当前状态快照

| 项 | 值 |
|---|---|
| 仓库 / 分支 | `tayhe/habits-tracker`，`main` |
| HEAD | **`eef45e3`**，**工作区 clean（0 变更）** |
| 本轮范围 | v4.1 `6331b41` → `eef45e3`，**11 个 commit，全部已 push** |
| CI | GitHub Actions **6 跑：5 绿 1 红**（红的那次 = N-06 测试侧时区缺陷，已修）；最近 3 跑 51s / 51s / 44s |
| 测试基线 | pytest **39**（`Asia/Shanghai` **与 `TZ=UTC` 都必须绿**）、`ruff` clean、对拍 **2225**、前端 **596 断言 + 163 绑定**、`template_bindings` **50 绑定**、UI 冒烟 **22 项** |
| 部署 | Docker 容器占 **15000（勿动）**、`server:app` 8000；冒烟自带 **15999** 隔离实例 |
| 已拍板决策 | CSP `'unsafe-eval'` **关闭 / won't fix**（重开条件与理由：§6.8.3）；视图拆分 A-06 **已完成**；浏览器冒烟已从"等桌面端"改为 **Playwright 无头** |

### 7.2 已闭环（不要再碰）

- §1 **13 个 bug 全修**（2 P1 / 6 P2 / 5 P3），逐条带复检证据（§6.1）
- §2 架构缺陷 **9/10**（只剩 A-07，条件触发）；§3 **六类测试缺口全补**
- 阶段：Phase 0/1/2/3 **100%**、Phase 4 **~90%**、Phase 5 **~60%**（明细 §6.2，决策 §6.8，路线 §6.9）

### 7.3 未完成工作（按优先级，接手从上往下挑）

| # | 项 | 触发条件 | 预估 | 怎么做 | 验收标准 |
|---|---|---|---|---|---|
| **1** | **CI 加 UI 冒烟 job**（唯一无条件建议做） | 无条件 | ~0.5h | `.github/workflows/ci.yml` 加 `ui-smoke` job，草案见 §7.6 | 新 job 绿；**故意改坏视图时该 job 必须变红** |
| 2 | Phase 4.3 连接策略（A-03 尾巴） | 想把连接获取收敛成 FastAPI dependency 时 | 1–2h | dependency 提供"每请求一 conn"，替代函数内反复 `get_db()` | `test_records_week_query_efficiency` 等现有测试仍绿 |
| 3 | Phase 5 剩余三小项 | 备份可靠性 / 可观测性有需求时 | 各 0.5–1h | ① 备份后 `PRAGMA quick_check`，失败告警 ② 结构化日志 + 请求 ID ③ 备份轮转补 53 周 / 跨年断言 | 每项配一条测试 |
| 4 | **A-07 进程内状态**（限流字典、后台任务单例） | **仅当**要多 worker / 多实例部署 | 1d+ | 限流与后台任务外置（Redis 等） | 多进程下限流仍生效的测试 |
| 5 | 抽出 `views/daily-picker.js` | `daily.js`（215 行）改动频繁时 | 0.5h | 浮层选择器独立成模块（−90 行） | `ui_smoke` 22 项全绿 |
| — | ~~CSP 去 `'unsafe-eval'`~~ | **已拍板关闭**（重开条件 = 暴露公网或面向不可信用户，§6.8.3） | — | — | — |

### 7.4 接手复检命令（先跑这个对齐基线）

```bash
cd ~/Projects/mine/habits-tracker
.venv/bin/python -m pytest -q && TZ=UTC .venv/bin/python -m pytest -q   # 两次都应 39 passed
.venv/bin/ruff check .
./scripts/check_bare_dates.sh      # 裸时钟守护，已覆盖 tests/
./scripts/check_frontend.sh        # node --check(app/lib/views) + 163 绑定 + 596 断言
./scripts/parity_check.sh          # 2225 例前后端对拍
./scripts/ui_smoke.sh              # 无头 UI 冒烟 22 项；首次需 uv run playwright install chromium
git status --short                 # 应为空
```

推送与 CI：`git push origin main`（gh 已认证）→ `gh run list --repo tayhe/habits-tracker` → `gh run watch <id> --repo tayhe/habits-tracker --exit-status`。

### 7.5 已知的坑（务必避开）

1. `.venv/bin/uvicorn` 的 shebang 指向已失效的旧路径 → 用 `uv run uvicorn`。
2. **测试里禁止 `date.today()` / `datetime.now().date()`**：宿主时区与 `clock.today()`（Asia/Shanghai）在 **16:00–24:00 UTC** 日历分叉 → **CI 每天 8 小时必挂、本地永远绿**（N-06 的教训）。`check_bare_dates.sh` 已扫描 `tests/`，测耗时仍可用 `datetime.now()`。
3. `check_template_bindings.mjs` **只收简写属性**：`bindings: { foo: bar }` 不会被识别，必须写 `foo,`（脚本会给出该 hint）。它 union 的是 `app.js` 唯一的 `return {` + `frontend/views/*.js` 的全部 `bindings: {`。
4. UI 冒烟端口 **15999** 与生产 **15000** 隔离：脚本每次 wipe 自己的 `DATA_DIR`（`/tmp/opencode/ui-smoke-data`），**若端口已占用会拒绝运行**（防止接管别人的实例）。
5. 登录限流 IP:User **5 次/分** → 频繁重跑可能 429；冒烟脚本自带全新实例，限流器随进程重置。
6. 需要在某个 commit 上单独验证时：`git worktree add -q --detach /tmp/opencode/wt-cX <commit>`，再用**绝对路径**的 `.venv/bin/python -m pytest`。
7. 生产容器跑在 15000，本地验证一律用 15999，**不要重启/重建生产容器**。

### 7.6 CI 冒烟 job 草案（#1 项可直接照做）

```yaml
  ui-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - run: uv sync --frozen
      - run: uv run playwright install --with-deps chromium
      - run: ./scripts/ui_smoke.sh
```

- `ui_smoke.sh` 自带隔离实例（`127.0.0.1:15999` + 独立 `DATA_DIR`，脚本会 `mkdir -p`），runner 上无需额外配置；`uv.lock` 已含 `playwright`（dev 依赖），故用 `--frozen` 可直接装。
- 脚本内"今天"取 `Asia/Shanghai`、后端走 `clock.py`，**在 UTC runner 上语义一致**，不受坑 #2 影响。
- 如需留证据，加一步 `actions/upload-artifact` 上传 `/tmp/opencode/ui-smoke-shots`（逐视图截图）。
- 预期 CI 从 ~45s 增到 **~90–120s**；若嫌慢，可给 `playwright install` 加 `cache: playwright`。

### 7.7 文档同步约定（防 A-08 复发）

改完代码后三处必须同步：`README.md`（结构树 / 测试清单 / 环境变量）、`HISTORY.md`（版本条目）、`fix-mimo.md`（§6 验收 + 本 §7 状态快照）。本项目已因文档漂移出过 2 次问题（A-08、N-03）。

---

## 附录 A — P1-01 / P2-03 / P2-04 / P2-06 复现脚本（修复后用于验收）

```python
# PYTHONPATH=. .venv/bin/python reproduce.py
import tempfile, pathlib
from datetime import date, timedelta
tmp = pathlib.Path(tempfile.mkdtemp())
from backend import config, database
database.DB_PATH = config.DB_PATH = tmp / "h.db"
database.init_db()
from fastapi.testclient import TestClient
from backend.main import app
c = TestClient(app)
c.post("/api/v1/auth/login", json={"username": "tayhe", "password": "parents"})

mon = date.today() - timedelta(days=date.today().weekday())
week = f"{mon.isocalendar()[0]}-W{mon.isocalendar()[1]:02d}"
c.put("/api/v1/records", json={"date": mon.isoformat(), "task_id": "en_recite", "completed": True})
print("归档前 weekly :", c.get(f"/api/v1/summary/weekly?week={week}").json()["英语"])
c.delete("/api/v1/tasks/en_recite")                       # 软删除
print("归档后 weekly :", c.get(f"/api/v1/summary/weekly?week={week}").json()["英语"])   # 期望 total_tasks 6
print("归档后 trend  :", c.get("/api/v1/summary/multi-week?weeks=1").json()[-1])        # 期望 total_tasks 6（与上一致）

print("week='garbage':", c.put("/api/v1/summary/fulfillment?week=garbage&fulfilled=true").status_code)  # 期望 400
print("parent 未来日期:", c.put("/api/v1/records", json={"date": (date.today()+timedelta(days=10)).isoformat(),
                                                        "task_id": "en_word", "completed": True}).status_code)  # 期望 400
for t in c.get("/api/v1/tasks").json():                   # 归档全部任务
    c.delete(f"/api/v1/tasks/{t['task_id']}")
print("全归档 week_completed_days:", c.get(f"/api/v1/records/week?date={mon.isoformat()}").json()["week_completed_days"])  # 期望 0
```

**2026-09-30 实测（修复后）**：三端口径 6/6/6 一致 ✅、garbage→400 ✅、未来日期→400 ✅、空周→0 ✅。

## 附录 B — P1-02 时区验证（容器内）

```bash
docker compose run --rm habits-tracker python -c "import datetime;print(datetime.date.today())"
# 对比宿主机日期：北京时间 00:00–08:00 之间执行，二者差一天即确认 P1-02
date +%F
```

## 附录 C — 前后端 ISO 周对拍（已执行，0 差异）

- `scripts/check-iso-week.mjs`：抽出 `app.js` 的 `getWeekStr/parseWeekStr`，遍历 2024-01-01 起 1500 天输出 `日期 周标签 该周周一`。
- `check-iso-week.py`：用 `backend.weeks.iso_week_label/parse_week_label` 输出同样格式。
- `diff` 结果：**0 mismatch** → 当前两套实现等价，Phase 4.5 把该脚本固化进 CI 即可。

## 附录 D — 现状基线

**修复前（v4.1, `6331b41`）**
```
pytest:      16 passed, 2 warnings（均为 TestClient cookie 弃用告警）
ruff:        All checks passed!  (E,F,W,I / line-length 100)
git status:  clean @ 6331b41
行数:        backend 1639 / frontend 1846 / tests 283
```

**第 1 轮复检时（2026-09-30，当时改动未提交）**
```
pytest:      27 passed, 2 warnings   (+11)
ruff:        All checks passed!
git status:  15 modified + 4 untracked（backend/clock.py, backend/repo.py, tests/*×3）
新增:        backend/clock.py(32) backend/repo.py(78)
             tests/test_summary_consistency.py(75) tests/test_clock_and_security.py(90) tests/test_repo.py(60)
裸日期调用:  grep "date.today()|datetime.now()" backend/ → 0 命中
死代码:      grep "week-earn|WeekEarn|UserCreate|progress_bar" → 0 命中
```

**当前（第 3 轮后，2026-09-30，`4903066` 已 push）**
```
pytest:      39 passed, 2 warnings   (+23)
ruff:        All checks passed!
git status:  clean @ 4903066（main，6 个新 commit，CI 首跑绿）
检查脚本:    check_bare_dates ✓ / parity_check 2225 ✓ / check_frontend 596+163 ✓
```

**第 4 轮后（2026-10-01，`b916fa0` 已 push）**
```
pytest:      39 passed（Asia/Shanghai 与 TZ=UTC 两种时区均绿）
ruff:        All checks passed!
git status:  clean @ b916fa0（main，累计 10 个新 commit，CI 3 跑全绿）
前端:        app.js 604 → 230 行 + frontend/views/ 5 模块（暴露面 50 绑定守恒）
新增脚本:    scripts/ui_smoke.{sh,py}（Playwright dev 依赖，22 项断言 + 逐视图截图）
检查脚本:    bare_dates ✓（已扩到 tests/）/ parity 2225 ✓ / frontend 596+163 ✓（含 views/ 语法）
             template_bindings ✓ 50 绑定（多来源收集）/ ui_smoke ✓ 22 项
```
