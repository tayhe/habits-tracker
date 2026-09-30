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
> 交付形态：**全部改动仍在工作区未提交**（18 modified + 11 untracked）

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
| **1 口径归一** | **~95%** | `repo.py` 收编 5 处 active-tasks + 4 处周聚合 + **batch 存在性校验（`repo.get_existing_active_task_ids`）**；`/records/week` **1 连接 3 查询**（有断言测试 `test_records_week_query_efficiency`）；死代码清零；索引恢复；**1.5 科目已由 `/config` 驱动**（`subjectList` / `weeklySubjects` computed，5 处硬编码 + 趋势表头表体 + 科目下拉全部改读） | multi-week 仍每周 1 次查询（1 连接，可接受，未做批量化） |
| **2 时钟收敛** | **100%** | `clock.py` + 全项目裸日期调用零残留 + mock 注入点；**`scripts/check_bare_dates.sh` 作为 pre-commit/CI hook**；**2.3 `cleanup` 改 `julianday()` 比较** | — |
| **3 安全健壮** | **~95%** | 3.1 ✅ 3.2 ✅ 3.3 ✅ 3.4 ✅ 3.7 ✅ **3.5 ✅（docs 门控 / CORS 收敛 / 安全头 + CSP）** **3.6 ✅（`INITIAL_*_PASSWORD` 环境变量）** **3.8 ✅（对齐 03:00 + `logging`）** 3.9 🔶 | 3.9 CSP 仍需 `'unsafe-eval'`（零构建 Vue 运行时模板编译），已无法再收紧；`/health` DB 可写探针归入 Phase 5 |
| **4 工程化** | **~75%** | **A-04 `DB_PATH` 单源**（`database.py` 动态读 `config.DB_PATH`，conftest 只 patch 一处，`test_seed_credentials_read_from_config` 验证）；**迁移字典 `MIGRATIONS` + 建表→迁移→播种顺序**；**对拍脚本进仓库并接 CI**（`scripts/parity_*` 2225 例）；**`parseDateLocal`**；**pre-commit + GitHub Actions**；前端纯函数拆到 `frontend/lib/`（4 模块） | **前端视图层拆分（A-06 / 4.4）未做**——在零前端测试网的前提下拆 `createApp` 视图属高风险重构，且已有浏览器冒烟验证，建议单独一轮 |
| **5 可选** | 0% | — | 按需 |

### 6.3 测试网对照（16 → 35 项，+19）

| 计划项 | 状态 | 说明 |
|---|---|---|
| T-1 归档口径三端一致 | ✅ | `test_archived_task_consistent_across_endpoints` |
| T-2 注入时钟窗口边界 | ✅ | `test_clock_mock_and_shanghai_timezone`；**N-04 已补**：conftest 增加 autouse `_reset_global_state`，每个用例前后自动 `set_mock_time(None)` + 清空限速器 |
| T-3 权限矩阵表驱动 | ✅ | 第 2 轮补齐 `child × {POST/PUT/DELETE /tasks}` 403 + `child GET /tasks` 200（`test_child_cannot_manage_tasks`） |
| T-4 未来日期策略 | ✅ | parent 400 + child 403 双断言 |
| T-5 week 校验 + 限流 | ✅ | week/60 上限 ✅；**登录端到端 429**（`test_login_rate_limit_returns_429`，conftest autouse 复位限速器防串测） |
| T-6 前端对拍 + 日期解析 | ✅ | `scripts/parity_check.sh`（2225 例：周标签/周界/解析/表情）+ `scripts/frontend_unit.mjs`（596 断言，含 `parseDateLocal` 与 `humanDetail`），均已接 CI |

### 6.4 本轮复检新发现（第 2 轮已全部闭环）

| ID | 级别 | 问题 | 证据 | 状态 |
|---|---|---|---|---|
| **N-01** | P2 | **把"静默假成功"改成了"看不懂的失败"**：后端 422 的 `detail` 是对象数组，前端 `api()` 直接 `showToast(err.detail)` → Toast 渲染 `[{'type': 'value_error', …}]` | 实测 422 detail 为 `[{type,loc,msg,input,ctx}]`；`app.js` 未做归一化 | ✅ 新建 `frontend/lib/errors.js`（`humanDetail`，字段中文标签 + 类型化渲染），429 单独分支；`frontend_unit.mjs` 8 例覆盖 |
| **N-02** | P2 | `TaskBase` 给 `reward=0.0`、`weekly_min=1` 加了默认值 → `TaskCreate` 必填变可选，`POST /tasks` 不带 reward 返回 **200**、静默建出 0 收益任务 | 复检 `POST {"task_id","subject","name"}` → 200 | ✅ `TaskCreate` 显式覆写为必填（`TaskUpdate` 仍全可选），`test_task_create_requires_reward_and_weekly_min` 断言缺字段与显式 null 均 422 |
| **N-03** | P2 | **文档漂移复发（A-08）**：README 结构树缺 `repo.py`/`clock.py`，`rules.py` 描述仍写"进度条"（已删），测试清单缺 3 个新文件；HISTORY 无本轮修复条目；`project-conventions` skill 未更新 | `grep -n "repo.py\|clock.py" README.md` 无命中 | ✅ README 结构树/测试清单/环境变量表/安全默认值重写，HISTORY 新增 **v4.2** 条目，`~/.claude/skills/project-conventions/SKILL.md` 已重写为"硬约定 + 提交前检查"速查（删掉与 README 重复且已过时的结构树/表名） |
| **N-04** | P3 | `clock.set_mock_time` 是模块级全局，靠各测试 `try/finally` 清理 → 一旦某个用例漏写，后续所有用例跑在假时间上（静默污染） | `tests/test_clock_and_security.py:12-24` | ✅ conftest 增加 autouse `_reset_global_state`，覆盖 mock 时钟与限速器两类全局状态 |
| **N-05** | P3 | `assert_editable_for_child` 现在同时约束 parent 的未来日期，名不副实 | `rules.py:34` | ✅ 改名 `assert_editable`，docstring 明确三档规则；`records.py` 2 处调用与 `test_rules.py` 同步 |

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

**流程提醒**：全部改动**尚未提交**。建议按阶段拆 commit（`fix: P1 归档口径与时区止血` → `refactor: repo/clock 收敛` → `fix: 安全与校验` → `chore: 检查脚本与 CI`），避免一次性大 diff 回滚困难；提交前先 `cp data/habits.db data/backups/pre-fix-$(date +%Y%m%d).db`。

### 6.6 第 2 轮补完记录（2026-09-30）

**验收命令与结果**（全部在仓库根目录执行）：

| 检查 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `.venv/bin/python -m pytest -q` | **35 passed**（27 → 35，新增 `tests/test_hardening.py` 8 项） |
| 代码风格 | `.venv/bin/ruff check .` | All checks passed |
| 裸时钟守护 | `./scripts/check_bare_dates.sh` | 通过（`backend/` 内 `date.today()` / `datetime.now()` 零命中） |
| 前后端对拍 | `./scripts/parity_check.sh` | **2225 cases match**（1500 天周标签 + 110 例周解析 + 153 例表情分级） |
| 前端检查 | `./scripts/check_frontend.sh` | **596 assertions** + 5 个模块语法检查 + **163 条模板绑定检查**通过 |
| CI / 钩子 | `.github/workflows/ci.yml`、`.pre-commit-config.yaml` | YAML 校验通过（本地未实际运行 pre-commit，需先安装） |
| 运行时冒烟 | `uvicorn` 起在 `127.0.0.1:15999`（`DATA_DIR=/tmp/opencode/smoke-data`，与生产 15000 容器隔离）+ curl 全链路 | `/` 与 `/app/**`（含 `lib/*.js`）全 200；登录 200；`/config` 返回 `subjects`；缺 `reward` 的 `POST /tasks` → **422**；未来日期 → **400**；`week=garbage` → **400**；`/docs`、`/openapi.json` → **404**；响应头含 nosniff / DENY / CSP；生产容器 15000 未受影响 |

> **浏览器冒烟未做**：`browser` 工具报 `No desktop browser is connected to this session`。替代验证 = 上表 curl 全链路 + `scripts/check_template_bindings.mjs`（163 条模板表达式对 `setup()` 返回值做静态交叉检查，可捕获 `v-for="sub in weeklySubject"` 这类只在运行时才暴露的笔误；已用故意注入的 typo 验证其会非零退出）。

**遗留项（按优先级）**：

1. **未提交**：18 modified + 11 untracked 仍在工作区，需按 §6.5 的阶段拆 commit，并先做 DB 快照。
2. **A-06 / Phase 4.4 前端视图层拆分**：`app.js` 仍是单个 `createApp({setup})`。本轮只抽了纯函数到 `frontend/lib/`（可被 Node 复用），视图拆分在零前端测试网下风险偏高，建议单独一轮并配合浏览器冒烟。
3. **Phase 5 可选项**：`/health` DB 可写探针、multi-week 批量化查询、CSP 去除 `'unsafe-eval'`（需给 Vue 换 runtime-only 构建 + 预编译模板）。
4. **CI 首次验证**：`.github/workflows/ci.yml` 尚未在真实 runner 上跑过（本地等价命令全绿），push 后留意首跑。
5. **浏览器冒烟**：桌面端会话连接后登录，切一遍雄心/每日/战果/征途四视图，重点看趋势表列头与任务管理的科目下拉（本轮改为 `subjectList` 驱动）。

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

**复检时（修复后，2026-09-30，改动未提交）**
```
pytest:      27 passed, 2 warnings   (+11)
ruff:        All checks passed!
git status:  15 modified + 4 untracked（backend/clock.py, backend/repo.py, tests/*×3）
新增:        backend/clock.py(32) backend/repo.py(78)
             tests/test_summary_consistency.py(75) tests/test_clock_and_security.py(90) tests/test_repo.py(60)
裸日期调用:  grep "date.today()|datetime.now()" backend/ → 0 命中
死代码:      grep "week-earn|WeekEarn|UserCreate|progress_bar" → 0 命中
```
