# 小鱼干·学习习惯追踪

一个帮助小朋友追踪每日学习习惯完成情况的 Web 应用。源自 Notion 模板，使用 Vue 3（原生 ESM 零构建）+ FastAPI 构建，支持局域网多设备访问。

## 功能特性

- **每日追踪**：以 Notion 风格表格展示一周 7 天的任务完成情况，支持点击切换完成状态与浮层添加任务
- **每周汇总**：按科目统计达标项目数和收益，激励小朋友坚持完成学习任务
- **双角色系统**：家长可管理任务和查看全部历史数据，小朋友可填写最近 7 天的完成情况
- **收益机制**：每个任务有单次预估收益和周最低完成次数，达标后按实际完成次数计入真实收益
- **多周趋势**：征途标签展示多周数据对比，含分科目达标率和爸爸兑现追踪
- **修改密码**：家长和小朋友均可在页面右上角自助修改密码
- **多设备访问**：支持局域网/公网内任意浏览器访问，支持移动端 PWA；提供专用安卓平板独立客户端（WebView 原生壳，支持沉浸式全屏、屏幕常亮、防误触打卡，详见 [android/README.md](android/README.md)）

## 运行与部署

### 方式一：Docker 容器化运行（推荐生产部署）

生产环境强烈推荐使用 Docker Compose。Compose 文件配置了 `restart: unless-stopped`，在服务器重启或 Docker 重启后服务会自动恢复。

```bash
git clone <仓库地址>
cd habits-tracker

# 一键构建并启动
docker compose up -d --build
```

访问 http://localhost:15000（或局域网 IP:15000）。数据与滚动备份会自动持久化挂载至宿主机 `./data` 目录。

### 方式二：本地开发环境

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <仓库地址>
cd habits-tracker

# 安装依赖（含开发与测试依赖）
uv sync --frozen

# 启动开发服务（端口 15000，开箱即用，无需配置 PYTHONPATH）
# 注意：.venv/bin/uvicorn 的 shebang 指向旧路径，坏了；启动服务用 uv run
uv run uvicorn backend.main:app --host 0.0.0.0 --port 15000

# 运行自动化规则与业务单元测试
.venv/bin/pytest

# 代码风格
.venv/bin/ruff check .

# 前后端逻辑一致性对拍（ISO 周算法 + 猫猫表情）与前端纯函数单测
./scripts/parity_check.sh
./scripts/check_frontend.sh

# 无头 UI 冒烟（真实浏览器：登录 → 五视图渲染 → subjectList 接线 → console 零错误，逐视图截图）
# 首次需先执行: .venv/bin/playwright install chromium
./scripts/ui_smoke.sh
```

> 可选：`pre-commit install` 后，每次提交会自动跑 ruff、对拍、时钟与前端检查
> （配置见 `.pre-commit-config.yaml`）。CI 见 `.github/workflows/ci.yml`（push 触发）。
> UI 冒烟**已进 CI**（独立 `ui-smoke` job，装无头 Chromium 后跑 `scripts/ui_smoke.sh`，
> 失败时上传逐视图截图）；本地首次需 `.venv/bin/playwright install chromium`
> （**别用 `uv run playwright ...`**，非 frozen 的重新解析会挑错平台 wheel，见下文[常见陷阱与避坑指南](#常见陷阱与避坑指南)）。

### 方式三：安卓平板客户端（APK）

项目在 `android/` 目录下提供了专为平板定制的 Android 客户端源码。

> [!IMPORTANT]
> **【构建规范】严禁在本地编译 Android APK**，避免本地拉取数 GB 编译镜像及产生庞大依赖缓存。构建已全权由 **GitHub Actions 云端自动化完成**。

- **获取安装包**：在 GitHub 仓库 **Actions** -> **Build Android APK** -> 最新成功的构建记录底部，下载 **Artifacts** (`habits-tracker-apk`) 即可获得 `app-release.apk`（约 4.5MB）。
- **触发构建**：向 `main` 分支提交任何涉及 `android/**` 的变更，或在 Actions 页面点击 **Run workflow** 即可在 2 分钟内由云端打出最新包。
- 平板专属优化（沉浸式全屏、常亮打卡、儿童防误触、隐形设置入口）详见 [android/README.md](android/README.md)。

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | `15000` | 服务端口 |
| `DATA_DIR` / `DB_PATH` / `BACKUP_DIR` | `./data/...` | 数据目录、数据库文件与备份目录（`DB_PATH` 是数据库路径唯一来源） |
| `MAX_BACKUPS` | `3` | 滚动备份保留份数 |
| `EDITABLE_DAY_WINDOW` | `7` | 小朋友可编辑的最近 N 天窗口 |
| `INITIAL_PARENT_PASSWORD` / `INITIAL_CHILD_PASSWORD` | `parents` / `child` | **仅在用户表为空时**用于播种初始账号，生产环境务必覆盖 |
| `INITIAL_PARENT_USERNAME` / `INITIAL_CHILD_USERNAME` | `tayhe` / `meow` | 同上，初始用户名 |
| `COOKIE_MAX_AGE` | `2592000`（30 天） | Session Cookie 有效期（秒） |
| `ENABLE_DOCS` | `0` | 置 `1` 才开放 `/docs`、`/redoc`、`/openapi.json` |
| `CORS_ORIGINS` | 空（关闭） | 逗号分隔的允许跨域来源；前端默认同源托管，无需开启 |
| `MAINTENANCE_HOUR` | `3` | 每日备份/Session 清理的执行小时（Asia/Shanghai） |
| `TZ` | 容器内为 UTC | **必须设为 `Asia/Shanghai`**，否则服务端「今天」比浏览器晚 8 小时（compose 已内置） |

### 安全默认值

- 交互式 API 文档 `/docs` 默认关闭（`ENABLE_DOCS=1` 才开启）。
- 默认不下发任何 CORS 头：前端由同一个服务同源托管，不存在合法的跨域请求。
- 所有响应附带 `X-Content-Type-Options`、`X-Frame-Options: DENY`、`Referrer-Policy` 与 CSP（`frame-ancestors 'none'`）。
- 登录接口按「来源 IP + 账号」双维度限速，连续 5 次失败后返回 429。

## 演示账号与权限矩阵

| 角色 | 用户名 | 默认密码 | 说明 |
|------|--------|----------|------|
| 家长 | tayhe  | parents  | 管理员权限，可管理任务、修改历史所有记录、标记兑现状态 |
| 小朋友 | meow | child    | 仅支持查看并编辑最近 7 天内的打卡记录 |

> 登录后可在页面右上角点击 🔑 自助修改密码。

### 权限矩阵

| 操作模块 | 家长（parent） | 小朋友（child） |
|---|---|---|
| 用户认证（登录/登出/修改密码） | ✅ | ✅ |
| 查看所有数据视图（雄心/每日/战果/征途） | ✅ | ✅ |
| 打卡记录填写与修改 | ✅（任意历史日期） | ✅（仅限最近 7 天窗口） |
| 任务定义管理（增删改查） | ✅ | ❌ |
| 标记爸爸是否兑现 | ✅ | ❌（仅只读查看） |

## 核心业务与收益算法

### 1. 每日预估收益 vs 每周确认收益
* **每日捕猎（本日预计收益）**：当天完成的所有任务单次收益之和（即时正反馈）：
  $$\text{本日预计收益} = \sum (\text{已完成任务的单次 reward})$$
* **一周战果（实际确认收益）**：每周汇总核算，只有达标任务才计入最终收益：
  - **实际完成次数 $\ge$ `weekly_min`（达标门槛） $\rightarrow$ 达标**：收益 = `单次收益 × 本周实际完成次数`（多做多得）；
  - **实际完成次数 $<$ `weekly_min` $\rightarrow$ 未达标**：收益 = 0。

### 2. 猫猫心情表情与进度条
系统根据完成率分级呈现猫猫表情与字符进度条：

| 完成率区间 | 心情表情 | 含义 |
|---|---|---|
| 100% | 😺🎉 | 大满贯（完全达标） |
| 75% ~ 99% | 😺 | 得意猫 |
| 50% ~ 74% | 😸 | 开心猫 |
| 25% ~ 49% | 😼 | 坚强猫 |
| 1% ~ 24% | 😾 | 生气猫 |
| 0% | 😿 | 小哭猫 |

进度条由 `▓`（已完成）与 `░`（未完成）组成，最多呈现 15 格。

## 数据模型（SQLite Schema）

数据库文件持久化在 `data/habits.db`，采用 WAL 模式，每周首次运行自动生成快照备份至 `data/backups/`（仅保留最新 3 份）。

### 1. `users` 用户表
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | 自增主键 |
| `username` | TEXT UNIQUE | 用户名 |
| `password_hash` | TEXT | bcrypt 加密哈希 |
| `role` | TEXT | 角色：'parent' 或 'child' |
| `created_at` | DATETIME | 注册时间 |

### 2. `tasks` 任务定义表
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | 自增主键 |
| `task_id` | TEXT UNIQUE | 唯一英文标识（如 en_word） |
| `subject` | TEXT | 科目：英语 / 数学 / 语文 / 体育（由后端 config.SUBJECTS 集中管控，Schema v4 已解除底层 CHECK 约束） |
| `name` | TEXT | 任务名称 |
| `reward` | REAL | 单次收益（鱼干） |
| `weekly_min` | INTEGER | 每周最低达标次数 |
| `sort_weight` | INTEGER | 排序权重（数值越大越靠前） |
| `deleted_at` | DATETIME | 软删除/归档时间戳（NULL 表示活跃） |
| `created_at` | DATETIME | 创建时间 |

> 📌 **任务清单与规划详情**：全部任务的具体定义、唯一代码（`task_id`）、门槛与收益测算已抽离收敛至 **[TASKS.md](TASKS.md)**（系统任务唯一真实信源）。

### 3. `daily_records` 每日打卡记录表
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | 自增主键 |
| `date` | DATE | 记录日期（YYYY-MM-DD） |
| `task_id` | TEXT FK | 关联任务 task_id |
| `completed` | BOOLEAN | 是否已完成 |
| `updated_at` | DATETIME | 最近更新时间 |

### 4. `sessions` 会话管理表
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | 自增主键 |
| `token` | TEXT UNIQUE | 32位安全随机 Session Token |
| `user_id` | INTEGER FK | 关联用户 id |
| `created_at` | DATETIME | 创建时间（超 30 天自动清理） |

### 5. `weekly_fulfillment` 爸爸兑现表
| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | 自增主键 |
| `week` | TEXT UNIQUE | ISO 周标识（YYYY-WXX） |
| `fulfilled` | BOOLEAN | 是否已兑现奖励 |
| `fulfilled_at` | DATETIME | 兑现操作时间 |
| `created_at` | DATETIME | 创建时间 |

## API 路由清单（`/api/v1`）

### 系统配置与健康检查
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/health` | 健康检查探针：`SELECT 1` + `BEGIN IMMEDIATE` 写探针，返回 WAL 模式与 schema 版本；数据库不可用时返回 **503**（容器 healthcheck 依赖） | 公开 |
| `GET` | `/api/v1/config` | 获取前端动态配置（可编辑天数窗口、科目列表 `subjects`） | 公开 |

### 认证接口 (`/auth`)
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `POST` | `/auth/login` | 用户登录并下发 HttpOnly Session Cookie（带防暴力破解限速） | 公开 |
| `POST` | `/auth/logout` | 注销并删除当前 Session | 登录用户 |
| `GET` | `/auth/me` | 获取当前登录用户信息 | 登录用户 |
| `PUT` | `/auth/password` | 修改当前用户密码（至少6位，旧 Session 全部吊销） | 登录用户 |

### 任务接口 (`/tasks`)
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/tasks` | 获取所有任务定义清单（仅展示未归档任务） | 登录用户 |
| `POST` | `/tasks` | 创建自定义新任务 | 仅 parent |
| `PUT` | `/tasks/{task_id}` | 修改任务属性（名称、科目、单次收益、周最低等） | 仅 parent |
| `DELETE` | `/tasks/{task_id}` | 软删除/归档任务（历史打卡数据完整保留） | 仅 parent |

### 打卡记录 (`/records`)
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/records/week?date=YYYY-MM-DD` | 获取指定日期所在整周7天的全部任务打卡矩阵（含标准 ISO week 标识） | 登录用户 |
| `GET` | `/records?date=YYYY-MM-DD` | 获取指定单日的打卡列表 | 登录用户 |
| `GET` | `/records/range?start=&end=` | 获取指定日期范围内的打卡记录（最大跨度 93 天） | 登录用户 |
| `PUT` | `/records` | 更新单条任务打卡状态 | 登录用户（child 仅限最近7天且≤今天；parent 允许历史日期） |
| `PUT` | `/records/batch` | 批量更新任务打卡状态 | 登录用户（child 仅限最近7天且≤今天；parent 允许历史日期） |

### 统计与兑现 (`/summary`)
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| `GET` | `/summary/daily?date=YYYY-MM-DD` | 单日打卡与预计收益汇总 | 登录用户 |
| `GET` | `/summary/weekly?week=YYYY-WXX` | 获取指定周的分科目达标统计与子任务明细 | 登录用户 |
| `GET` | `/summary/multi-week?weeks=N` | 获取最近 N 周的历史趋势对比数据 | 登录用户 |
| `GET` | `/summary/fulfillment?weeks=...` | 批量查询多周的爸爸兑现状态 | 登录用户 |
| `PUT` | `/summary/fulfillment?week=...&fulfilled=...` | 勾选/取消指定周的爸爸兑现状态 | 仅 parent |


## 技术选型与项目结构

- **后端**：Python 3.12+ / FastAPI / Uvicorn（FastAPI Lifespan 自动维护）
- **数据与存储**：SQLite（WAL 预写日志模式 + 每周滚动备份）/ Pydantic v2 / bcrypt
- **前端**：Vue 3（原生 ESM 零构建引入）/ 原生 CSS / PWA Web App Manifest
- **包管理**：uv
- **容器化**：Docker / Docker Compose

```
habits-tracker/
├── backend/          # FastAPI 后端标准包
│   ├── __init__.py   # 标识标准 Python Package
│   ├── main.py       # 入口、路由注册、安全响应头、CORS 开关、Lifespan 周期任务与全局异常拦截
│   ├── config.py     # 环境变量读取与配置项（端口、路径、安全开关、初始账号）
│   ├── clock.py      # 时钟唯一入口（Asia/Shanghai，测试可 set_mock_time 注入）
│   ├── models.py     # Pydantic 请求/响应模型（extra='forbid'，Create 与 Update 分离）
│   ├── database.py   # SQLite 连接（WAL）、建表、user_version 版本迁移、播种与滚动备份
│   ├── repo.py       # 唯一 SQL 数据访问层（Router 不再手写 SQL）
│   ├── auth.py       # Cookie 会话鉴权与过期 Session 清理
│   ├── weeks.py      # ISO 8601 标准周算法收敛与严格解析器
│   ├── rules.py      # 业务核心纯函数（猫猫表情、达标收益、assert_editable 权限窗口）
│   └── routers/      # API 路由拆分（auth, tasks, records, summary）
├── frontend/         # 前端静态单页（由 FastAPI 托管，零构建 ESM）
│   ├── index.html    # 声明式 SPA 模板（科目列表由 /config 驱动）
│   ├── app.js        # 应用装配：全局状态、api/鉴权/toast、视图组装与 switchView
│   ├── views/        # 5 个视图模块 ambition/daily/weekly/trend/tasks，各返回 { load, bindings }
│   ├── lib/          # 纯函数模块：dates / iso-week / progress / errors（Node 可直接导入）
│   ├── style.css     # Notion 极简风格样式
│   ├── manifest.json # PWA 渐进式 Web 应用配置
│   ├── assets/       # 图片与图标素材（PNG, SVG）
│   └── vendor/       # 离线自托管 Vue 3 运行时
├── scripts/          # 本地 / CI 检查脚本
│   ├── parity_check.sh + parity_backend.py + parity_frontend.mjs  # 前后端周算法与表情对拍
│   ├── check_frontend.sh + frontend_unit.mjs                       # 前端语法检查与纯函数单测
│   ├── check_template_bindings.mjs                                 # 模板 ↔ setup/views 绑定静态交叉检查
│   ├── check_bare_dates.sh                                         # 禁止绕过 clock.py 直接读时钟（含 tests/）
│   └── ui_smoke.sh + ui_smoke.py                                   # 无头浏览器 UI 冒烟（需 chromium）
├── tests/            # 自动化测试套件（pytest + TestClient）
│   ├── conftest.py   # 临时库隔离 + 全局状态（mock 时钟、限速器）自动复位
│   ├── test_api_regressions.py      # P0/P1 回归测试与边界校验
│   ├── test_clock_and_security.py   # mock 时钟、未来日期拒绝、限速器有界性
│   ├── test_hardening.py            # 文档关闭 / 安全头 / CORS / 权限矩阵 / 429 端到端
│   ├── test_summary_consistency.py  # 日 / 周 / 趋势三端口径一致性
│   ├── test_repo.py                 # repo 层查询与索引有效性
│   ├── test_rules.py                # 业务规则与备份轮转
│   ├── test_phase5.py               # /health 就绪探针与 multi-week 批量化
│   ├── test_weeks.py                # ISO 周算法跨年边界
│   └── test_concurrency.py          # 并发写入与 Busy Timeout 锁
├── .github/workflows/ci.yml # CI：ruff + pytest + 对拍 + 前端检查
├── .pre-commit-config.yaml  # 可选本地提交钩子（同一批检查）
├── data/             # SQLite 数据库与备份（已 gitignore）
├── Dockerfile        # 纯 Python 生产镜像（非 root 用户 appuser 运行）
├── docker-compose.yml# 端口映射、卷挂载、TZ=Asia/Shanghai 与 healthcheck 探针
└── pyproject.toml    # 项目依赖、测试配置与 Ruff Linter 规范
```

## 开发规约与架构硬约定

> **修改本仓库代码前必读**。以下约定违反会导致测试或生产静默出错：

1. **时钟必须且只能经 `backend/clock.py`**：
   - 业务逻辑固定使用 `Asia/Shanghai` 时区。
   - 严禁在 `backend/` 与 `tests/` 中裸调 `date.today()` 或 `datetime.now().date()`（`scripts/check_bare_dates.sh` 会在 pre-commit/CI 中强制扫描拦截）。
   - **原因**：宿主时区与 UTC 在每日 16:00–24:00 出现日历分叉，若直接使用宿主日期，会导致 CI 每天固定 8 小时红单而本地全绿。
2. **SQL 查询必须且只能经 `backend/repo.py`**：
   - Router 层禁止手写 SQL。归档任务过滤条件 `deleted_at IS NULL` 统一收敛在 repo 层，杜绝各端统计口径不一致。
3. **数据库路径单源 `config.DB_PATH`**：
   - `database.py` 动态读取 `config.DB_PATH`（非 import 期快照），测试仅需 patch `config.DB_PATH` 这一处。
4. **前端日期字符串解析必须使用 `parseDateLocal()`**：
   - 在 [`frontend/lib/dates.js`](frontend/lib/dates.js) 中定义。
   - 严禁使用 `new Date('YYYY-MM-DD')`（其按 UTC 午夜解析，在东八区会偏差落入前一天）。
5. **科目清单由后端驱动**：
   - 来自 `GET /api/v1/config` 的 `subjects`（当前支持：英语、数学、语文、体育）。前端 `SUBJECT_INFO` 负责颜色与展示 emoji；数据库 `tasks` 表使用 `TEXT NOT NULL` 解除底层写死枚举限制（Schema v4 迁移已移除旧 CHECK 约束），由 `backend/config.py` 与 Pydantic 校验器作为单一真相来源（SSOT）集中管控合法科目。
6. **错误提示格式归一**：
   - 后端 422/429 的 `detail` 可能是 Pydantic 对象数组，前端必须先经 [`frontend/lib/errors.js`](frontend/lib/errors.js) 的 `humanDetail()` 处理再传给 Toast，防止渲染出 `[object Object]`。
7. **数据表命名约定**：
   - `users`
   - `tasks`（含 `deleted_at` 软删除）
   - `daily_records`（注意：表名不是 `records`，且**无 `user_id`**，约束为 `UNIQUE(date, task_id)`）
   - `sessions`
   - `weekly_fulfillment`
8. **角色与行为边界**：
   - 家长（parent）：可管理任务、标记兑现、修改历史打卡，但**禁止填写未来日期（后端返回 400）**。
   - 小朋友（child）：仅允许打卡且限制在最近 7 天窗口内（`d <= today`）；任何任务管理写操作返回 403。
9. **端口与实例隔离**：
   - 生产服务固定在端口 **15000**；UI 冒烟测试自带 **15999** 独立实例和专属临时数据目录（端口被占时拒绝运行以防误触生产）。
10. **提交前必须运行的基线检查（五项全绿方可提交）**：
    ```bash
    .venv/bin/python -m pytest -q && .venv/bin/ruff check . \
      && ./scripts/check_bare_dates.sh \
      && ./scripts/check_frontend.sh \
      && ./scripts/parity_check.sh
    ```
    改动前端视图代码后，需另跑 `./scripts/ui_smoke.sh`（真实无头浏览器 22 项断言）。

---

## 常见陷阱与避坑指南

1. **依赖管理必须用 `uv sync --frozen`**：
   - 在 ARM Linux（如 aarch64）环境上，手敲 `uv run <package>`（非 frozen 重新解析）可能会误挑 x86-64 平台的 driver wheel，导致 `Exec format error`（例如 Playwright 崩溃）。
   - 装依赖必须用 `uv sync --frozen`；安装 Playwright 浏览器必须用 `.venv/bin/playwright install chromium`。
2. **UI 冒烟归档截图中的深色药丸不是 Bug**：
   - `scripts/ui_smoke.sh` 保存的全页截图中，底部居中可能会出现一个深色圆角小块。
   - 这是应用自身的 `#toast` 元素（靠 `translateY` 隐藏），`full_page=True` 截图撑大画布时被拍进画面。在真实用户屏幕折叠线以下完全不可见，**请勿当作 UI Bug 修改**。
3. **前端模板绑定检查规则**：
   - `check_template_bindings.mjs` 静态交叉检查只识别简写属性语法 `bindings: { foo, bar }`，不支持 `bindings: { foo: bar }`。
4. **CSP 保留 `'unsafe-eval'` 的架构决策**：
   - 本项目定位于局域网/内网零构建轻量化应用，Vue 3 采用 native ESM 运行时编译器（runtime-compiler），需要动态编译模板。
   - 经评估关闭（won't fix）：仅当系统未来暴露公网或有不可信外部用户输入时，再考虑引入打包构建流程移除 unsafe-eval。
5. **`/summary/week-earn` 与 `rules.calculate_reward`**：
   - 前端当前未调用该接口，系有意保留的历史端点，不是漏接线。
6. **前端静态资源缓存破坏（Cache Busting）**：
   - 为避免客户端浏览器强缓存导致容器部署更新后依然加载旧版 CSS/JS（例如新增科目后旧版样式依然生效、Emoji 显示为默认图钉 📌 等），FastAPI 根路由（`/`）已注入 `Cache-Control: no-cache, no-store, must-revalidate`。
   - 凡对 `frontend/style.css` 或 `frontend/app.js` 作出破坏性结构修改时，应在 `frontend/index.html` 中的引用链接追加或递增版本号参数（如 `?v=YYYYMMDD_vX`），确保各端无感即时获取最新界面。

---

## 后续按需演进路线（Backlog）

1. **多进程部署支持（A-07 进程内状态解耦）**：
   - 触发条件：未来业务扩展需要 `uvicorn --workers N` 多进程部署时。
   - 改造点：将 `BoundedRateLimiter` 内存字典和单例后台定时维护任务外置至 Redis。
2. **连接生命周期 Dependency 化（Phase 4.3）**：
   - 触发条件：希望将数据库连接获取进一步收敛为 FastAPI 请求级依赖注入时。
   - 改造点：依赖提供“每请求一连接”，替代业务函数内的 `repo.get_connection()`。
3. **运维与可观测性增强（Phase 5）**：
   - 触发条件：对容灾备份可靠性有更高要求时。
   - 改造点：备份后执行 `PRAGMA quick_check`、增加请求链路 ID 与结构化日志、补齐 53 周跨年轮转断言。

---

## 相关文档

- [TASKS.md](TASKS.md) — 任务规划清单与唯一信源（各学科项目定义、指标与收益）
- [HISTORY.md](HISTORY.md) — 版本迭代历史与变更记录

## 许可证

私有项目
