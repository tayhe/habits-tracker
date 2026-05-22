# Habits_Tracker 项目规范 v2.1

## 1. 项目概述

### 背景
- 原系统：Notion 上的"小鱼干学习习惯追踪系统"（Notion 模板）
- 问题：WPS 多维表格实现效果未达预期，暂停
- 新方案：HTML 单页应用 + Python FastAPI 后端

### 目标
- 完美复刻 Notion Habits_Tracker 的产品体验（见 source/notion_screenshot_habits_tracker.png）
- 支持多浏览器局域网访问
- 支持家长（管理员）和小朋友（记录）双账号体系
- 数据存储在服务器 SQLite 数据库

### 使用场景
- 太和（家长）：在局域网内任意浏览器管理任务、记录完成情况
- 小鱼干（小朋友）：在任意设备查看进度、填写每日完成次数

---

## 2. 技术方案

### 技术栈
| 层级 | 技术选型 | 说明 |
|---|---|---|
| 后端 | Python 3 + FastAPI | 轻量、高性能、自动 OpenAPI 文档 |
| 数据库 | SQLite | 零配置、单文件、够用 |
| 前端 | 纯 HTML + CSS + JS | 无框架依赖，单文件部署 |
| 认证 | Session + Cookie | 简单够用，局域网场景 |

### 文件结构
```
habits-tracker/
├── AGENT.md                 # 本规范文档
├── backend/
│   ├── main.py              # FastAPI 入口、路由定义
│   ├── config.py            # 集中配置（端口、Cookie、编辑窗口等）
│   ├── models.py            # Pydantic 数据模型
│   ├── database.py          # SQLite 连接、初始化、context manager
│   ├── auth.py              # 鉴权逻辑（parent/child）+ FastAPI 依赖
│   ├── routers/
│   │   ├── auth_router.py   # 认证路由（login/logout/me）
│   │   ├── tasks.py         # 任务定义 CRUD（含认证）
│   │   ├── records.py       # 每日记录 CRUD
│   │   └── summary.py       # 汇总查询
│   └── requirements.txt
├── frontend/
│   └── index.html           # 单页应用（内联 CSS/JS）
├── data/
│   └── habits.db            # SQLite 数据库文件（Git 忽略）
└── source/
    └── notion_export/       # 原始 Notion 导出数据（只读）
```

---

## 3. 数据模型

### 表：users
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 用户ID |
| username | TEXT UNIQUE | 用户名 |
| password_hash | TEXT | bcrypt 哈希 |
| role | TEXT | 'parent' 或 'child' |
| created_at | DATETIME | 创建时间 |

### 表：tasks（任务定义）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 任务ID |
| task_id | TEXT UNIQUE | 任务标识符（英文 slug） |
| subject | TEXT | 科目：英语/数学/语文 |
| name | TEXT | 显示名称 |
| reward | REAL | 单次收益值 |
| weekly_min | INTEGER | 周最低完成次数 |
| sort_weight | INTEGER | 排序权重 |
| created_at | DATETIME | 创建时间 |

**15条初始数据（来自 source/notion_export）**
```
英语单词     en_word      0.1  5次/周
英语绘本     en_picture   0.2  5次/周
英语背诵     en_recite    1.0  1次/周
英语课       en_class     0.3  5次/周
英语听力     en_listen    0.1  5次/周
英语阅读100  en_read100   0.2  2次/周
英语语法     en_grammar   0.5  2次/周
数学思维课程 math_course  0.5  2次/周
举一反三     math_extra   0.2  5次/周
数学预习课后练习 math_prac 0.2  4次/周
计算         math_calc    0.2  5次/周
语文晨读     cn_morning   0.1  4次/周
课外阅读     cn_read      0.2  2次/周
书法         cn_write     0.1  5次/周
阅读100题   cn_read100   0.1  5次/周
```

### 表：daily_records（每日记录）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 记录ID |
| date | DATE | 记录日期 |
| task_id | TEXT FK | 关联任务 |
| completed | BOOLEAN | 是否完成（true/false） |
| updated_at | DATETIME | 更新时间 |

**说明**：每条 record 代表某日某任务子项的完成状态（完成/未完成），非数字计数

### 表：weekly_summary（每周汇总，自动计算不存储）
按 (week_number, subject) 聚合：
- 本周完成天数（单日完成率 ≥ 50% 算达标）
- 完成率
- 本周总收益

---

## 4. API 设计

所有接口前缀 `/api/v1`

### 认证
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | /auth/login | 登录，返回 session | 公开 |
| POST | /auth/logout | 登出 | 登录用户 |
| GET | /auth/me | 获取当前用户信息 | 登录用户 |

### 任务管理
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /tasks | 获取所有任务 | 登录用户 |
| POST | /tasks | 新增任务 | parent |
| PUT | /tasks/{task_id} | 修改任务 | parent |
| DELETE | /tasks/{task_id} | 删除任务 | parent |

### 每日记录
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /records/week?date=YYYY-MM-DD | 获取指定日期所在周的7天数据 | 登录用户 |
| GET | /records?date=YYYY-MM-DD | 获取指定日期各任务完成情况 | 登录用户 |
| GET | /records/range?start=YYYY-MM-DD&end=YYYY-MM-DD | 获取日期范围内各任务完成情况 | 登录用户 |
| PUT | /records | 单条更新某日某任务完成状态 | 登录用户（child 仅限最近3天） |
| PUT | /records/batch | 批量更新某日各任务完成状态 | 登录用户（child 仅限最近3天） |

### 汇总
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /summary/daily?date=YYYY-MM-DD | 每日汇总（含表情符号） | 登录用户 |
| GET | /summary/weekly?week=YYYY-WXX | 每周汇总（按科目） | 登录用户 |
| GET | /summary/week-earn?date=YYYY-MM-DD | 本周累计收益 | 登录用户 |

---

## 5. 界面设计（复刻 Notion）

### 5.1 每日追踪视图（Notion 风格表格）

**所有用户共享同一视图**：日期为行、科目为列的表格

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  🐟 小鱼干·学习习惯追踪                         [用户名] [角色] [登出]       │
├──────────────────────────────────────────────────────────────────────────────┤
│  [每日追踪]  [每周汇总]  [任务管理]                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ◀ 上周                                                              下周 ▶  │
│                                                                              │
│  ┌──────────┬──────────────────┬──────────────────┬──────────────────┬──────┬──────┐
│  │ Date     │ 📖 英语7项        │ 🔢 数学4项        │ 📝 语文4项        │ Σ 预 │ 🐟   │
│  ├──────────┼──────────────────┼──────────────────┼──────────────────┼──────┼──────┤
│  │ 05/19 周一│ 英语绘本 英语课    │ 计算 举一反三      │ 晨读 阅读         │ 0.9  │ 🐟   │
│  │ 05/20 周二│ 英语单词          │                  │ 书法             │ 0.1  │ 😭   │
│  │ 05/21 周三│                  │ 数学思维课程      │                  │ 0.5  │ 😭   │
│  │ 05/22 周四│ 英语听力 英语阅读  │ 计算             │ 晨读             │ 0.4  │ 😭   │
│  │ 05/23 周五│ 英语绘本 英语背诵  │ 举一反三 计算     │ 阅读100题        │ 1.5  │ 🐟   │
│  │ 05/24 周六│                  │                  │                  │ 0    │ 😭   │
│  │ 05/25 周日│                  │                  │                  │ 0    │ 😭   │
│  └──────────┴──────────────────┴──────────────────┴──────────────────┴──────┴──────┘
│                                                                              │
│  今日完成: 7/15                                本周已获: 1.2 鱼干            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 表头样式

| 列 | 样式 |
|---|---|
| Date | 左对齐，sticky 左侧，灰色背景 |
| 📖 英语 | 蓝色文字 #2563EB，显示任务数（如"英语7项"） |
| 🔢 数学 | 橙色文字 #D97706，显示任务数 |
| 📝 语文 | 绿色文字 #059669，显示任务数 |
| Σ 本日预 | 居中，显示当日收益数字 |
| 🐟 本日进度 | 居中，显示进度 emoji |

### 5.3 日期行样式

| 类型 | 样式 |
|---|---|
| 历史（>3天前） | 任务芯片为淡化色，不可点击 |
| 最近3天（可编辑） | 任务芯片为正常色，可点击切换 |
| 今日 | 整行蓝色背景 #EFF6FF，日期加粗蓝色 |

### 5.4 任务芯片（Chip）交互

- **已完成**：彩色背景药丸（英语蓝/数学黄/语文绿），显示任务名
- **未完成**：同色系淡化背景 + 淡化文字，显示任务名
- **点击切换**：调用 `PUT /records` API，实时更新芯片状态和缓存
- **只读（历史）**：淡化色 + `cursor: default`，点击无反应

### 5.5 Footer 统计

```
今日完成: 7/15                            本周已获: 1.2 鱼干
```

- 格式：`今日完成: {已完成任务数}/{总任务数}`
- 格式：`本周已获: {累计收益} 鱼干`

### 5.6 周导航

- 左箭头 ◀：切换到上一周
- 右箭头 ▶：切换到下一周
- 显示当前周范围（如 "05/19 ~ 05/25"）

---

## 6. 每周汇总视图

- 顶部：周次选择器
- 主体：三栏（英语/数学/语文），每栏显示本周完成天数/总天数 + 进度条 + 总收益
- 底部：全科总收益

---

## 7. 任务管理视图（仅 parent）

- 任务列表（可编辑名称/收益/周最低次数/排序权重）
- 新增任务表单

---

## 8. 权限矩阵

| 操作 | parent | child |
|---|---|---|
| 登录 | ✅ | ✅ |
| 查看所有视图 | ✅ | ✅（无任务管理） |
| 填写完成次数 | ✅（任意日期） | ✅（最近3天可编辑） |
| 管理任务定义 | ✅ | ❌ |
| 导入历史数据 | ✅ | ❌ |

---

## 9. 表情计算规则

```python
def progress_emoji(completed_tasks: int, total_tasks: int) -> str:
    """
    单日完成率 = completed_tasks / total_tasks

    表情判断：
    - 完成率 >= 100% → 🐟🐡
    - 完成率 >= 50% → 🐟
    - 完成率 < 50% → 😭
    """
```

---

## 10. 部署方案

### 启动方式（局域网）
```bash
cd habits-tracker/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 18765
```

访问地址：`http://<服务器IP>:18765`

### 数据库初始化
首次启动时自动建表、插入初始15条任务和2个用户。

### 端口
使用 **18765**（与现有服务不冲突）

---

## 11. 实现状态

### Phase 1：后端骨架 ✅
- [x] 项目目录创建
- [x] FastAPI 骨架（含 CORS 配置）
- [x] SQLite 数据库初始化
- [x] User / Task 模型
- [x] 登录认证接口

### Phase 2：核心 API ✅
- [x] Tasks CRUD
- [x] DailyRecords 读写（含 `/records/week` 7天批量接口）
- [x] DailySummary / WeeklySummary（含 `/summary/week-earn`）
- [x] 权限控制（child 用户限制最近3天编辑）

### Phase 3：前端 ✅
- [x] HTML + CSS 框架（复刻 Notion 风格）
- [x] 统一7天网格视图（所有用户共享）
- [x] 每周汇总视图
- [x] 任务管理视图（仅 parent）
- [x] 登录页

### Phase 4：测试与数据迁移
- [x] 后端 API 测试（curl 验证通过）
- [x] 浏览器端到端测试（登录页、认证、日期显示、任务管理）
- [ ] 局域网访问验证
- [ ] 历史数据从 Notion CSV 导入（可选）

---

## 12. 重构工作记录（2026-05-22）

### 已完成的重构

#### A. 基础设施
- [x] **新建 `config.py`**：集中管理端口（18765）、Cookie有效期（30天）、编辑窗口（3天）、进度表情阈值等
- [x] **添加数据库索引**：`idx_records_date_task`、`idx_sessions_token`、`idx_sessions_user`
- [x] **修复 main.py 重复 root()**：删除第102-104行重复函数，保留正确的文件读取版本

#### B. 认证统一
- [x] **统一 auth 依赖**：`main.py` 删除重复定义，改用 `from auth import get_current_user, require_parent`
- [x] **为 tasks 路由添加认证**：GET 使用 `get_current_user`，POST/PUT/DELETE 使用 `require_parent`
- [x] **修复 require_parent 的 Depends 注入**：原函数缺少 `Depends(get_current_user)`，导致 FastAPI 将 user 参数误判为 request body

#### C. 数据库连接安全
- [x] **添加 `get_db()` context manager**：替代手动 `conn.close()` 模式，消除连接泄漏风险

#### D. 前端修复
- [x] **修复 `getWeekStart` 错误**：`-date.getDay()` → `-(date.getDay() || 7)`，修复周日计算错误
- [x] **统一 `formatDate` 为本地时间**：`toISOString()` (UTC) → 本地年月日拼接，消除跨时区 bug
- [x] **抽取 `getISOWeekStart()` 和 `getWeekStr()`**：统一 ISO 周计算，消除 weekly view 导航重复代码
- [x] **修复无限刷新问题**：`api()` 中 401 处理由 `location.reload()` 改为 `showLogin()`

#### E. 代码清理
- [x] **清理 `records.py` 重复函数**：`get_records_for_date` 和 `get_tasks_for_date` 职责合并
- [x] **删除未使用模型**：`CSVImportRequest` 在 `models.py` 中定义但路由未实现，已删除
- [x] **修复 summary.py 的函数引用**：更新为使用重命名后的函数

### 验证结果（已通过）
| 测试项 | 结果 |
|--------|------|
| `GET /api/v1/tasks` (parent) | ✅ |
| `GET /api/v1/tasks` (child) | ✅ 已登录用户可访问 |
| `DELETE /tasks/{id}` (child) | ✅ 正确返回 403 "Parent access required" |
| `DELETE /tasks/{id}` (parent) | ✅ 删除成功 |
| `POST /tasks` (child) | ✅ 403 拒绝 |
| `/records/week` API | ✅ 返回7天数据 |
| `/summary/daily` API | ✅ 正确返回 15 项任务 + emoji |
| `/summary/weekly` API | ✅ 按科目汇总 |
| Child 更新今日记录 | ✅ 成功 |
| Child 更新 12 天前记录 | ✅ 正确拒绝 (403) |
| 前端登录页 | ✅ 无无限刷新 |

### 待进一步优化（后续）
- [ ] Service 层抽取（TaskService、RecordService、SummaryService）
- [ ] Pydantic Enum 验证（subject 字段）
- [ ] 全局异常处理（统一错误格式）
- [ ] 配置化演示账号密码（环境变量）
- [ ] 自动化测试套件
- [ ] 部署配置（Dockerfile / systemd）

---

## 13. 重构工作记录 v2（2026-05-23）

### A. 安全修复
- [x] **补全 API 认证**：`GET /records`、`GET /records/range`、`GET /summary/daily`、`GET /summary/weekly` 添加 `Depends(get_current_user)`
- [x] **启用外键约束**：`get_connection()` 中添加 `PRAGMA foreign_keys = ON`
- [x] **修复 CORS 配置**：`allow_credentials=False`（前端同源，无需跨域凭证）
- [x] **Session 过期机制**：`validate_session` 检查 `created_at` 是否超过 `COOKIE_MAX_AGE`

### B. 后端代码质量
- [x] **全面使用 `get_db()` context manager**：所有 14 处数据库访问改为 `with get_db() as conn:` 模式
- [x] **清理未使用导入**：`lru_cache`、`Path`、`datetime`、`HTTPException`、`List`、重复 `os`/`date_class`/`timedelta` 导入
- [x] **统一错误处理**：`summary.py` 无效周格式返回 HTTPException 400；`tasks.py` 仅捕获 `sqlite3.IntegrityError`
- [x] **抽取 `build_day_records()` 公共函数**：消除 4 处重复的 DayRecords 构建逻辑
- [x] **删除 `get_tasks_for_date` 别名**：`summary.py` 直接导入 `get_records_for_date`
- [x] **统一 ISO 周计算**：使用 `date.isocalendar()` 替代手动计算，抽取 `get_iso_week_range()`
- [x] **修复静默成功**：`update_task`/`delete_task` 检查 `cursor.rowcount`，不存在则返回 404
- [x] **提取科目常量**：`config.SUBJECTS` 供 `database.py` 和 `summary.py` 共用
- [x] **认证路由分离**：新建 `routers/auth_router.py`，从 `main.py` 迁移 login/logout/me

### C. 前端修复
- [x] **修复 Cookie forbidden header**：删除手动 Cookie 设置，改用 `credentials: 'same-origin'`
- [x] **修复 XSS 风险**：添加 `escapeHtml()` 工具函数，所有动态数据插入前先转义
- [x] **修复空响应崩溃**：`api()` 中 `r.json()` 改为检查 `resp.text` 后再解析
- [x] **修复变量遮蔽**：`toggleRecord` 中 `r` 改为 `resp`，`.find(r =>)` 回调改为 `rec`
- [x] **合并 week-start 函数**：删除 `getISOWeekStart()`，统一使用 `getWeekStart()` + `getWeekStr()`
- [x] **补充 `#weekNav2` CSS**：weekly view 导航按钮居中样式
- [x] **抽取 `isSameDay()` 工具函数**：消除重复的日期比较模式
- [x] **登录改用 `api()` helper**：统一错误处理
- [x] **使用 `crypto.randomUUID()`**：替代 `Date.now()` 生成 task_id

### D. 项目基础设施
- [x] **创建 `.gitignore`**：排除 `data/`、`__pycache__/`、`.venv/`、`.env` 等
- [x] **统一使用 uv**：删除旧 `venv/`，用 `uv venv --python 3.12` 重建
- [x] **更新 `requirements.txt`**：版本同步，移除未使用的 `httpx`
- [x] **修复用户名 typo**：`taihe` → `tayhe`（database.py + frontend）
- [x] **更新 AGENT.md**：移除 CSV 导入、补充 `/records/range`、更新实现状态

---

## 14. 已修复的问题

### Bug 1：Cookie 参数名错误
- **问题**：`get_current_user(token=Cookie(None))` 中参数名 `token` 导致 FastAPI 查找名为 `token` 的 cookie，实际 cookie 名为 `session_token`
- **修复**：将参数名改为 `session_token=Cookie(None)`
- **涉及文件**：`auth.py`、`main.py`

### Bug 2：validate_session 返回值 key 不一致
- **问题**：返回 `user_id` 但 `main.py` 中 `me()` 函数需要 `id`
- **修复**：统一返回 `{"id", "username", "role"}`
- **涉及文件**：`auth.py`

### Bug 3：tasks 路由缺少认证（安全漏洞）
- **问题**：`tasks.py` 的 POST/PUT/DELETE 端点未添加认证依赖，任何人可创建/修改/删除任务
- **修复**：添加 `Depends(get_current_user)` 和 `Depends(require_parent)` 依赖
- **涉及文件**：`routers/tasks.py`

### Bug 4：require_parent 缺少 Depends 注入
- **问题**：`require_parent(user: dict)` 函数参数未用 `Depends(get_current_user)` 注入，FastAPI 将 `user` 视为 request body，导致 DELETE/PUT/POST 返回 422 "Field required"
- **修复**：改为 `require_parent(user: dict = Depends(get_current_user))`
- **涉及文件**：`auth.py`

### Bug 5：前端 getWeekStart 周日计算错误
- **问题**：`addDays(date, -date.getDay())` 在周日（getDay()===0）时减0天，返回周日而非周一
- **修复**：改为 `addDays(date, -(date.getDay() || 7))`
- **涉及文件**：`frontend/index.html`

### Bug 6：formatDate 使用 UTC 导致日期偏差
- **问题**：`toISOString()` 返回 UTC 日期，与本地时间混用可能导致跨时区错误
- **修复**：改为本地年月日拼接：`${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
- **涉及文件**：`frontend/index.html`

### Bug 7：前端登录后无限刷新
- **问题**：`api()` 函数在收到 401 时执行 `location.reload()`，未登录用户首次访问时触发 `/auth/me` 返回 401，导致无限刷新
- **修复**：401 时调用 `showLogin()` 而非 `location.reload()`
- **涉及文件**：`frontend/index.html`

### Bug 8：main.py 重复 root() 函数
- **问题**：两个同名 `root()` 函数导致后者覆盖前者
- **修复**：删除第102-104行的重复定义
- **涉及文件**：`main.py`

---

## 15. Bug 修复与前端重设计（2026-05-23）

### 修复的问题

#### Bug 9：每周汇总和任务管理页面空白
- **问题 1**：任务管理导航按钮缺少 `data-view="tasks"` 属性，`switchView('tasks')` 执行时 `querySelector` 返回 `null`，`.classList.add('active')` 抛出 TypeError，后续代码（显示视图、加载数据）全部不执行
- **问题 2**：CSS 中 `#weeklyView { display: none; }` 和 `#taskMgmtView { display: none; }` 导致 `switchView()` 中 `style.display = ''` 无法覆盖，元素永远不可见
- **修复**：给按钮添加 `data-view="tasks"`；`switchView()` 改用 `style.display = 'block'` 而非 `''`；移除 CSS 中的 `display: none`（由 JS 控制显隐）
- **涉及文件**：`frontend/index.html`

#### Bug 10：每日追踪布局不符合 Notion 设计
- **问题**：原实现为"科目为行、7天为列"的网格布局，每个单元格显示 checkbox。与 Notion 截图的"日期为行、科目为列"的表格布局完全不同
- **修复**：完全重写 `renderWeekGrid()`，改为 Notion 风格的表格布局：
  - **日期为行**（纵向，每行一天）
  - **科目为列**（英语/数学/语文，表头显示 emoji + 科目名 + 任务数）
  - **任务芯片（chip）** 替代 checkbox：已完成任务显示为彩色药丸，未完成为灰色轮廓，点击切换完成状态
  - **汇总列**：Σ 本日预（每日收益）+ 🐟 本日进度（emoji）
  - **今日行**：蓝色背景高亮
- **涉及文件**：`frontend/index.html`（CSS + JS `renderWeekGrid()` + `toggleRecord()`）

#### Bug 11：勾选内容切换日期后消失
- **问题**：`renderWeekGrid()` 从 `weekData.days[0].records` 构建网格结构。若周一（day 0）无记录，网格渲染为零行，没有任何可点击的项。看起来像数据未保存，实际是网格结构依赖了 day 0 的数据
- **修复**：作为 Bug 10 重设计的一部分解决——新实现始终渲染所有任务芯片，不依赖某一天是否有记录

### UI 变更详情

#### 旧布局（已废弃）
```
科目行 × 7天列的网格，每个单元格内有 checkbox 列表
```

#### 新布局（Notion 风格）
```
┌──────────┬──────────────────┬──────────────────┬──────────────────┬────────┬────────┐
│ Date     │ 📖 英语7项        │ 🔢 数学4项        │ 📝 语文4项        │ Σ 本日预│ 🐟 进度 │
├──────────┼──────────────────┼──────────────────┼──────────────────┼────────┼────────┤
│ 05/19 周一│ 英语绘本 英语课    │ 计算 举一反三      │ 晨读 阅读         │ 0.9    │ 🐟     │
│ 05/20 周二│ 英语单词          │                  │ 书法             │ 0.1    │ 😭     │
│ ...      │ ...              │ ...              │ ...              │ ...    │ ...    │
└──────────┴──────────────────┴──────────────────┴──────────────────┴────────┴────────┘
```

#### 任务芯片样式
| 科目 | 背景 | 文字 | 边框 |
|------|------|------|------|
| 英语（已完成） | #DBEAFE | #2563EB | #BFDBFE |
| 数学（已完成） | #FEF3C7 | #92400E | #FDE68A |
| 语文（已完成） | #D1FAE5 | #065F46 | #A7F3D0 |
| 只读状态 | 各科淡化色 | 淡化色 | 淡化色 |

### 验证结果
| 测试项 | 结果 |
|--------|------|
| JS 语法检查 | ✅ 无错误 |
| HTML 标签平衡 | ✅ 86 开 / 86 闭 |
| `PUT /records` 单条更新 | ✅ 数据持久化正确 |
| `GET /records/week` 返回 7 天 × 15 任务 | ✅ |
| `GET /summary/weekly` 返回 4 科目汇总 | ✅ |
| `GET /tasks` 返回 15 条任务 | ✅ |

---

## 16. 已知约束与注意事项


- 小朋友（child）账号只能修改最近3天记录，不能修改更早历史
- 每周汇总按周次（ISO week number）计算
- 日期使用 YYYY-MM-DD 格式（API），MM/DD 格式（显示）
- 所有时间使用 Asia/Shanghai 时区
- 数据库文件 `data/habits.db` 不加入 Git

### 环境要求
- Python 3.12+
- 推荐使用 `uv` 创建虚拟环境：`uv venv --python 3.12 .venv`
- 依赖安装：`uv pip install fastapi uvicorn pydantic python-multipart bcrypt python-dateutil httpx`

---

## 17. 演示账号

| 角色 | 用户名 | 密码 |
|---|---|---|
| 家长（parent） | tayhe | tayhe2026 |
| 小朋友（child） | meow | meow2026 |

---

_Last updated: 2026-05-23 | v2.2 Bug 修复与 Notion 布局重设计_