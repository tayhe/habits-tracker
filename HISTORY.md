# Habits_Tracker 变更历史

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
- 修复 XSS 风险：添加 `escapeHtml()` 工具函数
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
