# Habits_Tracker 变更历史

---

## 2026-09-30 v4.2 — 架构审计（fix-mimo.md）落地：口径归一、时钟收敛、安全默认值与工程化

本版本对应 `fix-mimo.md` 的分阶段修复计划及其复检验收（详见该文档 §4 / §6）。

### Phase 1 · 查询口径归一（P1-01）
- **唯一 SQL 层**：新建 `backend/repo.py`，所有 Router 不再手写 SQL；归档任务的 `deleted_at IS NULL` 过滤集中于一处。
- **周/日/趋势三端口径一致**：`/summary/weekly` 补上归档任务过滤，实测三端达标口径 6/6/6 完全一致（原为 15/14/14）。

### Phase 2 · 时钟收敛（P1-02）
- **新建 `backend/clock.py`**：时区固定 `Asia/Shanghai`，提供 `now()/now_utc()/today()`，测试可用 `set_mock_time` 注入；后端全部裸 `date.today()` / `datetime.now()` 归零，并由 `scripts/check_bare_dates.sh` 常驻守护。
- **容器时区**：`docker-compose.yml` 与 `Dockerfile` 显式 `TZ=Asia/Shanghai`，消除「服务端今天比浏览器晚 8 小时」的错位打卡。

### Phase 3 · 安全与健壮性
- **API 攻击面收敛**：`/docs`、`/redoc`、`/openapi.json` 默认关闭（`ENABLE_DOCS=1` 才开启）；默认不下发任何 CORS 头（`CORS_ORIGINS` 显式配置才启用）。
- **响应安全头**：统一中间件附加 `X-Content-Type-Options`、`X-Frame-Options: DENY`、`Referrer-Policy` 与 CSP（`frame-ancestors 'none'`）。
- **初始口令环境变量化**：`INITIAL_PARENT_PASSWORD` / `INITIAL_CHILD_PASSWORD` 等仅在用户表为空时播种，生产必须覆盖。
- **维护任务对齐 03:00**：每日备份与 Session 清理改按 `MAINTENANCE_HOUR`（Asia/Shanghai）定时，`print` 全面改为 `logging`。
- **限速器有界内存**：`BoundedRateLimiter` 按 IP/账号双维度、条目上限 + 过期剪枝，连续 5 次失败返回 429。

### Bug 修复
- **N-01 错误提示可读化**：新建 `frontend/lib/errors.js` 的 `humanDetail()`，把 422/429 的 Pydantic `detail` 数组渲染成中文可读 Toast（原为 `[object Object]`）。
- **N-02 创建任务契约**：`TaskCreate` 恢复 `reward` / `weekly_min` 必填，缺字段返回 422 而非静默落成 0 / 1。
- **P2-08 UTC 解析错日**：新增 `parseDateLocal()`，替换 `new Date('YYYY-MM-DD')` 的 UTC 午夜解析（Asia/Shanghai 下会落到前一天）。
- **N-05 权限函数更名**：`assert_editable_for_child` → `assert_editable`，反映其对 parent 未来日期同样拒绝（400）的语义。

### Phase 1.5 / 4 · 结构与工程化
- **科目由后端驱动**：前端 5 处「英语/数学/语文」硬编码改读 `/config` 的 `subjects`，`SUBJECT_INFO` 仅作展示样式兜底。
- **前端纯函数模块化**：日期、ISO 周、表情、错误归一抽至 `frontend/lib/`，浏览器与 Node 共用同一实现。
- **`DB_PATH` 单源**：`database.py` 不再拷贝 `config.DB_PATH`，测试只需 patch `config` 一处。
- **迁移字典化**：`user_version` 迁移改为 `MIGRATIONS` 注册表，建表 → 迁移 → 播种顺序执行。
- **检查脚本与 CI**：新增 `scripts/`（前后端周算法与表情对拍、前端单测、裸时钟守护）、`.pre-commit-config.yaml` 与 `.github/workflows/ci.yml`；**push 后 GitHub Actions 首跑通过**（41s，6 项检查全绿）。
- **无头 UI 冒烟（`scripts/ui_smoke.sh` + `ui_smoke.py`，Playwright 为 dev 依赖）**：起隔离实例（`127.0.0.1:15999`、独立 `DATA_DIR`）后走真实 Chromium 完成登录、五视图非空渲染、`subjectList` 接线（趋势表头 + 任务科目下拉）、播种数据落表为收益、console/pageerror/HTTP ≥400 全零，共 **22 项断言** + 逐视图截图。已用「注入 `subjectList` 取值错误」的变异验证其**会非零退出**——该类回归 pytest、静态模板绑定检查与 curl 均不可见。
- **测试网扩容**：pytest 16 → 39（新增权限矩阵、429 端到端、安全头、契约、repo 层与 Phase 5 探针测试），另加 2225 例前后端对拍与 596 条前端断言。

### Phase 5 首批
- **`/health` 真实就绪探针**：`SELECT 1` + `BEGIN IMMEDIATE` 写探针（`busy_timeout=3s`，卡在 compose 的 5s 超时内），返回 WAL 模式与 `user_version`；数据库不可用时返回 503，容器 healthcheck 不再"DB 挂了也报 ok"。
- **multi-week 批量化**：`/summary/multi-week` 由「每周一条 count 查询」改为「整段范围一条查询 + Python 按 ISO 周分桶」，26 周从 26 次查询降到 1 次；分桶复用 `weeks.iso_week_label`，与 `/summary/weekly` 永不漂移，并有单查询回归测试兜底。

---

## 2026-09-29 v4.1 — 架构缺陷根治、ISO 周算法归一与 P0/P1 缺陷修复

### P0 缺陷止血与数据完整性保障
- **任务软删除机制**：`tasks` 表新增 `deleted_at` 字段（通过 `PRAGMA user_version = 2` 自动迁移），物理删除改为软删除（归档）。彻底解决由于外键约束引发的删除任务 500 崩溃，同时保障历史打卡记录和统计账单完整不丢。
- **任务科目动态修改生效**：`TaskUpdate` 模型补全 `subject` 字段，并在所有核心请求模型增加 `extra="forbid"`，杜绝非法或未知字段被静默忽略产生的“假成功”。
- **登录失败交互反馈**：修复前端 `api()` 吞噬 401 导致密码输错无任何反应的问题，增加错误 Toast 提示。
- **登出幽灵会话彻底销毁**：修正登出接口 Cookie 参数名绑定（`token` -> `session_token`），确保登出后服务端 session 记录物理删除。
- **全局异常处理与并发锁保护**：全局捕获 `sqlite3.IntegrityError`（409）与 `sqlite3.OperationalError`（503 锁提示）；连接开启 `timeout=30.0` 与 `PRAGMA busy_timeout = 30000`，杜绝局域网并发写锁死。

### ISO 8601 周算法收敛与跨年死锁根治
- **新建权威周计算模块**：新增 `backend/weeks.py`，统一提供标准 `iso_week_label`、`monday_of`、`sunday_of` 与严格解析器 `parse_week_label`（周号越界如 `W99` 直接返回 400）。
- **根除跨年错周与翻页死循环**：
  - 后端统一用 ISO 年推导周标签，彻底解决 `date.year` 跨年周编号撞名问题；
  - 前端 `getWeekStr` 与 `parseWeekStr` 重构为标准 ISO 8601 算法，彻底解决在特定年份按“上一周”无限循环停留在同周的问题；
  - `/records/week` 接口响应下发权威 `week` 字段供前端直接消费。

### 业务规则解耦与查询性能优化
- **业务规则下沉纯函数**：新建 `backend/rules.py`，收纳猫猫表情分级（`progress_emoji`）、进度条（`progress_bar`）、达标收益结算（`calculate_reward`）和儿童编辑窗口校验（`assert_editable_for_child`），消除 Router 间反向耦合。
- **消除 N+1 数据库查询风暴**：
  - `/records/range` 增加 93 天最大跨度防护，从逐日单次连接查询优化为单连接 2 条聚合 SQL，耗时从 28s 降至毫秒级；
  - `/summary/multi-week` 将数据库连接和 tasks 查询移出循环外，消除 26 次重复连接。
- **自动事务纪律与备份容错**：`get_db()` 上下文管理器实现正常退出自动 `commit`、异常自动 `rollback`；周备份自动修剪在跨卷调用 `trash-put` 失败时自动安全 fallback 到直接删除。
- **改密安全吊销**：用户修改密码后，立即注销该用户所有历史 Session，并为当前操作设备签发新 Token。

### 真实自动化测试网建立与容器加固
- **彻底重构测试套件**：废弃原先 4/6 空转的伪测试，新增 `tests/conftest.py`（临时库与 Client fixture）、`tests/test_api_regressions.py`、`tests/test_weeks.py` 和 `tests/test_concurrency.py`，形成 16 项真实运行的高覆盖防回归网。
- **代码规范接入 Ruff**：配置 `pyproject.toml` 中的 `[tool.ruff]`，通过 `uv run ruff check` 自动规范代码风格与导入。
- **容器安全加固**：Dockerfile 新建非 root 用户 `appuser`（UID/GID 1002）运行，`docker-compose.yml` 增加 `healthcheck` 健康检查探针与显式端口映射。

---

## 2026-09-16 v4.0 — 前端 Vue 3 零构建迁移 + 健壮性与架构深度优化


### 前端 Vue 3 零构建与响应式重构
- **零构建引入 Vue 3**：引入本地自托管的浏览器原生 ESM 版本（`frontend/vendor/vue.esm-browser.prod.js`），完全脱离 Node.js 构建链
- **模块化解耦**：将原来 1740+ 行的单文件解耦为声明式模板（`index.html`）、核心响应式逻辑（`app.js`）以及样式表（`style.css`）
- **移动端 PWA 支持**：新增 `frontend/manifest.json` 与移动端 Touch 图标配置，支持在手机与 iPad 浏览器中“添加到主屏幕”作为全屏 App 运行
- **静态素材收纳**：新建 `frontend/assets/` 统一收拢 `dedenne.png` 与 `favicon.svg`

### 后端架构规范化与配置增强
- **消除 PYTHONPATH 约束**：新增 `backend/__init__.py` 并全面重构为标准相对包导入，开箱即用，无需再设置 `PYTHONPATH=backend`
- **环境变量配置支持**：`config.py` 支持 `PORT`、`DATA_DIR`、`MAX_BACKUPS`、`COOKIE_MAX_AGE` 等环境变量覆盖
- **模型升级**：Pydantic 模型全面升级使用 `model_config = ConfigDict(from_attributes=True)`，消除 V2 弃用警告

### 存储健壮性与自动维护
- **SQLite WAL 模式**：启用 `PRAGMA journal_mode = WAL`，读写互不阻塞，增强异常断电抗损坏能力
- **每周滚动备份**：每周自动生成快照备份至 `data/backups/habits_YYYY_wWW.db`，严格保留最新 3 份，历史旧备份自动移入回收站
- **过期 Session 定期回收**：FastAPI `lifespan` 启动及每 24 小时自动清理过期会话
- **数据库版本控制**：引入 `PRAGMA user_version` 原地轻量 Schema 迁移机制

### 测试套件与工程清理
- **自动化单元测试**：建立 `tests/` 目录并接入 `pytest`，对收益结算、达标门槛、7天编辑期限和备份修剪等核心业务规则建立测试防护网
- **清理冗余工具链**：移除未使用的 Node.js/Playwright 残留文件，将 `CLAUDE.md` 全部核心说明合并入 `README.md` 并移除冗余文档

---

## 2026-05-24 — 一周战果数据统一 + 收益术语澄清

### 一周战果页面数据源统一
- `/summary/weekly` 响应新增 `tasks` 字段，包含每个子任务的进度（`completed_count`、`qualified`）
- 前端一周战果页不再调用 `/records/week`，改为单一数据源 `/summary/weekly`
- 修复卡片头部（达标项目数/收益）与子项进度条不一致的问题

### 收益术语澄清
- 每日捕猎页底部 "本周已获" → "本周预期收益"（无条件累计所有已完成任务）
- `WeekRecords.week_total_earn` → `WeekRecords.expected_earn`（后端模型字段重命名）
- 明确区分：预期收益（每日捕猎）vs 实际达标收益（一周战果）

### 清理冗余代码
- 删除 `config.py` 中未使用的 `SESSION_TOKEN_BYTES` 和 `PROGRESS_EMOJI_THRESHOLDS`
- 删除 `database.py` 中未使用的 `SUBJECTS` 别名
- 删除 `source/` 目录（Notion 导出素材）
- 删除 `frontend/index.html` 中无目标的 `a` 标签 CSS 规则
- 更新 `AGENT.md` 目录树和 API 文档

---

## 2026-05-23 v3.0 — 收益逻辑修正 + uv 迁移 + Bug 修复

### 收益计算逻辑重写
- **weekly summary 收益规则修正**：达标后按实际完成次数计算（`reward × completions`），而非固定 `weekly_min` 次
- **weekly summary 查询重写**：改为按 task_id 分组统计完成次数，替代原来按 date 分组的错误逻辑
- **前端 weekly view 更新**："完成天数" → "达标项目"，分母从 7 改为实际任务数

### 项目迁移到 uv
- 删除旧 `backend/.venv` 和 `backend/requirements.txt`
- 新建 `pyproject.toml`（项目根目录），依赖与原 requirements.txt 一致
- `uv sync` 在项目根目录创建新 `.venv`
- 启动方式：`PYTHONPATH=backend uv run uvicorn backend.main:app --port 15000`
- 删除冗余的 `info/` 和 `status/` 目录（旧 venv 残留）

### 端口变更
- 项目端口从 18765 改为 15000（`config.py`）

### Bug 修复
- **Bug 12：今天（周六）缺少 "+" 按钮**
  - 原因：`currentWeekStart` 保留了 `new Date()` 的时间偏移（如 09:39），但 `today` 被归零到午夜（00:00）。计算出的 Saturday 为 09:39 > 00:00，导致 `saturday <= today` 为 false
  - 修复：在 `renderWeekGrid` 中添加 `currentWeekStart.setHours(0, 0, 0, 0)`

- **Bug 13：每周汇总切换周显示 NaN-WNaN**
  - 原因：`new Date("2026-W21")` 返回 Invalid Date，JavaScript 无法解析 ISO 周字符串
  - 修复：新增 `parseWeekStr()` 函数，通过 ISO 周计算公式从 1 月 4 日推导周一日期

- **Bug 14：家长账号受3天编辑限制**
  - 原因：前端 `isEditable` 判断未区分用户角色
  - 修复：`currentUser.role === 'parent'` 时跳过3天限制

- **Bug 15：表头"本日预计收益"显示不全**
  - 原因：列宽 90px 不足，表头文字被截断为"Σ 本日预..."
  - 修复：列宽增至 110px，表头改为完整文字"Σ 本日预计收益"

### Chrome 远程调试集成
- 发现 WSL 可通过 `localhost:9222` 连接 Windows Chrome 远程调试
- 使用 Playwright `chromium.connectOverCDP()` 控制浏览器进行自动化测试

---

## 2026-05-23 v2.2 — Bug 修复与 Notion 布局重设计

### 修复的问题

#### Bug 9：每周汇总和任务管理页面空白
- **问题 1**：任务管理导航按钮缺少 `data-view="tasks"` 属性，`switchView('tasks')` 执行时 `querySelector` 返回 `null`，`.classList.add('active')` 抛出 TypeError
- **问题 2**：CSS 中 `#weeklyView { display: none; }` 和 `#taskMgmtView { display: none; }` 导致 `switchView()` 中 `style.display = ''` 无法覆盖
- **修复**：给按钮添加 `data-view="tasks"`；`switchView()` 改用 `style.display = 'block'`；移除 CSS 中的 `display: none`

#### Bug 10：每日追踪布局不符合 Notion 设计
- 原实现为"科目为行、7天为列"的网格布局，每个单元格显示 checkbox
- 完全重写 `renderWeekGrid()`，改为 Notion 风格：日期为行、科目为列、任务芯片替代 checkbox

#### Bug 11：勾选内容切换日期后消失
- `renderWeekGrid()` 从 `weekData.days[0].records` 构建网格结构，若周一无记录则网格渲染为零行
- 作为 Bug 10 重设计的一部分解决

---

## 2026-05-23 v2.1 — 安全修复与代码质量提升

### 安全修复
- 补全 API 认证：`GET /records`、`GET /records/range`、`GET /summary/daily`、`GET /summary/weekly` 添加 `Depends(get_current_user)`
- 启用外键约束：`PRAGMA foreign_keys = ON`
- 修复 CORS 配置：`allow_credentials=False`
- Session 过期机制：检查 `created_at` 是否超过 `COOKIE_MAX_AGE`

### 后端代码质量
- 全面使用 `get_db()` context manager（14 处）
- 清理未使用导入
- 统一错误处理
- 抽取 `build_day_records()` 公共函数
- 统一 ISO 周计算，抽取 `get_iso_week_range()`
- 修复静默成功：`update_task`/`delete_task` 检查 `cursor.rowcount`
- 提取科目常量：`config.SUBJECTS`
- 认证路由分离：新建 `routers/auth_router.py`

### 前端修复
- 修复 Cookie forbidden header：改用 `credentials: 'same-origin'`
- 修复 XSS 风险：Vue 文本插值天然转义（早先计划的 escapeHtml 工具函数在 Vue 零构建迁移后由框架原生接管）
- 修复空响应崩溃：`api()` 中检查 `resp.text` 后再解析
- 修复变量遮蔽
- 合并 week-start 函数
- 登录改用 `api()` helper
- 使用 `crypto.randomUUID()` 生成 task_id

### 项目基础设施
- 创建 `.gitignore`
- 修复用户名 typo：`taihe` → `tayhe`

---

## 2026-05-22 v2.0 — 重构

### 基础设施
- 新建 `config.py`：集中管理配置
- 添加数据库索引
- 修复 main.py 重复 root() 函数

### 认证统一
- 统一 auth 依赖
- 为 tasks 路由添加认证
- 修复 require_parent 的 Depends 注入

### 数据库连接安全
- 添加 `get_db()` context manager

### 前端修复
- 修复 `getWeekStart` 周日计算错误
- 统一 `formatDate` 为本地时间
- 修复无限刷新问题

---

## 已修复的 Bug 汇总

| # | 日期 | 问题 | 修复 |
|---|------|------|------|
| 1 | 05-22 | Cookie 参数名错误 | 参数名改为 `session_token` |
| 2 | 05-22 | validate_session 返回值 key 不一致 | 统一返回 `{"id", "username", "role"}` |
| 3 | 05-22 | tasks 路由缺少认证 | 添加 `Depends(get_current_user)` 和 `require_parent` |
| 4 | 05-22 | require_parent 缺少 Depends 注入 | 改为 `Depends(get_current_user)` |
| 5 | 05-22 | getWeekStart 周日计算错误 | `-(date.getDay() \|\| 7)` |
| 6 | 05-22 | formatDate 使用 UTC | 改为本地年月日拼接 |
| 7 | 05-22 | 前端登录后无限刷新 | 401 时调用 `showLogin()` |
| 8 | 05-22 | main.py 重复 root() 函数 | 删除重复定义 |
| 9 | 05-23 | 每周汇总/任务管理页面空白 | 添加 `data-view` 属性，修复 CSS display |
| 10 | 05-23 | 每日追踪布局不符合 Notion 设计 | 完全重写 renderWeekGrid() |
| 11 | 05-23 | 勾选内容切换日期后消失 | 重设计解决 |
| 12 | 05-23 | 今天缺少 "+" 按钮 | `currentWeekStart.setHours(0,0,0,0)` |
| 13 | 05-23 | 每周汇总 NaN-WNaN | 新增 `parseWeekStr()` |
| 14 | 05-23 | 家长账号受3天限制 | `isEditable` 增加角色判断 |
| 15 | 05-23 | 表头文字截断 | 增大列宽，补全文字 |
