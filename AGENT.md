# Habits_Tracker 项目规范 v3.0

## 1. 项目概述

### 背景
- 原系统：Notion 上的"小鱼干学习习惯追踪系统"
- 新方案：HTML 单页应用 + Python FastAPI 后端

### 目标
- 复刻 Notion Habits_Tracker 的产品体验
- 支持多浏览器局域网访问
- 支持家长（管理员）和小朋友（记录）双账号体系
- 数据存储在服务器 SQLite 数据库

### 使用场景
- 太和（家长）：管理任务、记录任意日期的完成情况
- 小鱼干（小朋友）：查看进度、填写最近3天的完成情况

---

## 2. 技术方案

### 技术栈
| 层级 | 技术选型 | 说明 |
|---|---|---|
| 后端 | Python 3 + FastAPI | 轻量、高性能、自动 OpenAPI 文档 |
| 数据库 | SQLite | 零配置、单文件 |
| 前端 | 纯 HTML + CSS + JS | 无框架依赖，单文件部署 |
| 认证 | Session + Cookie | 简单够用，局域网场景 |
| 包管理 | uv | 替代 pip + venv |

### 文件结构
```
habits-tracker/
├── AGENT.md                 # 本规范文档
├── HISTORY.md               # 变更历史记录
├── pyproject.toml           # 项目元数据和依赖（uv 管理）
├── uv.lock                  # 依赖锁定文件
├── backend/
│   ├── main.py              # FastAPI 入口、路由注册、静态文件挂载
│   ├── config.py            # 集中配置（端口、Cookie、编辑窗口等）
│   ├── models.py            # Pydantic 数据模型
│   ├── database.py          # SQLite 连接、初始化、context manager
│   ├── auth.py              # 鉴权逻辑（parent/child）+ FastAPI 依赖
│   └── routers/
│       ├── auth_router.py   # 认证路由（login/logout/me）
│       ├── tasks.py         # 任务定义 CRUD（含认证）
│       ├── records.py       # 每日记录 CRUD
│       └── summary.py       # 汇总查询（每日/每周）
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
| reward | REAL | 单次预估收益值 |
| weekly_min | INTEGER | 周最低完成次数（达标门槛） |
| sort_weight | INTEGER | 排序权重 |
| created_at | DATETIME | 创建时间 |

**15条初始数据**
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
| completed | BOOLEAN | 是否完成 |
| updated_at | DATETIME | 更新时间 |

### 表：sessions
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PRIMARY KEY | 会话ID |
| token | TEXT UNIQUE | Session token |
| user_id | INTEGER FK | 关联用户 |
| created_at | DATETIME | 创建时间 |

---

## 4. 收益计算逻辑（核心）

### 每日预估收益（本日预计收益）
每日追踪页面显示的"本日预计收益"是**预估值**：
```
本日预计收益 = Σ (每个已完成任务的 reward)
```
这只是当天完成情况的即时反馈，不代表最终收益。

### 每周真实收益（每周汇总确认）
最终收益在每周汇总中确认，规则：
- 每个任务有 `weekly_min`（周最低完成次数）
- **本周该任务完成次数 ≥ weekly_min → 达标**，收益 = `reward × 本周实际完成次数`
- **本周该任务完成次数 < weekly_min → 未达标**，收益 = 0

```
示例：英语背诵 reward=1.0, weekly_min=1
  本周完成2次 → 达标 → 收益 = 1.0 × 2 = 2.0
  本周完成0次 → 未达标 → 收益 = 0

示例：英语单词 reward=0.1, weekly_min=5
  本周完成3次 → 未达标 → 收益 = 0
  本周完成5次 → 达标 → 收益 = 0.1 × 5 = 0.5
```

### 每周汇总展示
每周汇总卡片显示每个科目的达标情况：
- **达标项目**：该科目中有多少任务达标 / 总任务数
- **进度条**：达标比例
- **收益**：该科目所有达标任务的收益之和

---

## 5. API 设计

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
| GET | /records/range?start=&end= | 获取日期范围内的记录 | 登录用户 |
| PUT | /records | 更新单条记录 | 登录用户（child 仅限最近3天） |
| PUT | /records/batch | 批量更新记录 | 登录用户（child 仅限最近3天） |

### 汇总
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /summary/daily?date=YYYY-MM-DD | 每日汇总 | 登录用户 |
| GET | /summary/weekly?week=YYYY-WXX | 每周汇总（按科目） | 登录用户 |
| GET | /summary/week-earn?date=YYYY-MM-DD | 本周累计收益 | 登录用户 |

---

## 6. 界面设计

### 6.1 每日追踪视图（Notion 风格表格）

日期为行、科目为列的表格。每个科目列显示已完成的任务芯片和 "+" 添加按钮。

```
┌──────────┬──────────────────┬──────────────────┬──────────────────┬────────────┬────────┐
│ Date     │ 📖 英语7项        │ 🔢 数学4项        │ 📝 语文4项        │ Σ 本日预计收益│ 🐟 进度 │
├──────────┼──────────────────┼──────────────────┼──────────────────┼────────────┼────────┤
│ 05/21 周四│ 单词 背诵 课 听力  │ +               │ +               │ 1.5        │ 😭     │
│ 05/22 周五│ 绘本 背诵 课 听力  │ 思维课程 预习练习  │ 晨读 课外阅读     │ 2.6        │ 🐟     │
│ 05/23 周六│ 绘本 +           │ +               │ 课外阅读 +       │ 0.4        │ 😭     │
└──────────┴──────────────────┴──────────────────┴──────────────────┴────────────┴────────┘

今日完成: 2/15                                      本周已获: 4.5 鱼干
```

### 6.2 日期行样式
| 类型 | 样式 | 可编辑 |
|---|---|---|
| 历史（child: >3天前） | 淡化芯片，不可点击 | ❌ |
| 可编辑范围 | 正常芯片，可点击切换 | ✅ |
| 今日 | 蓝色背景 #EFF6FF，日期加粗蓝色 | ✅ |

**注意**：家长账号可编辑所有日期，不受3天限制。

### 6.3 任务芯片交互
- **已完成**：彩色药丸（英语蓝/数学黄/语文绿），点击取消
- **未完成**：不显示（通过 "+" 按钮的下拉菜单添加）
- **"+" 按钮**：虚线框，点击弹出未完成任务下拉列表

### 6.4 每周汇总视图
四个卡片（英语/数学/语文/总计），每个显示：
- 达标项目数/总任务数
- 进度条（达标比例）
- 收益（鱼干）

### 6.5 任务管理视图（仅 parent）
任务列表，可编辑名称/收益/周最低次数/排序权重，支持新增和删除。

---

## 7. 权限矩阵

| 操作 | parent | child |
|---|---|---|
| 登录 | ✅ | ✅ |
| 查看所有视图 | ✅ | ✅（无任务管理） |
| 填写完成情况 | ✅（任意日期） | ✅（仅最近3天） |
| 管理任务定义 | ✅ | ❌ |

---

## 8. 表情计算规则

### 每日进度表情
```python
def progress_emoji(completed_tasks, total_tasks):
    rate = completed_tasks / total_tasks
    if rate >= 1.0: return "🐟🐡"  # 全部完成
    if rate >= 0.5: return "🐟"    # 过半
    return "😭"                     # 不足一半
```

### 每周汇总表情
```python
# 使用相同的 progress_emoji 函数
# completed_tasks = 本周达标任务数
# total_tasks = 该科目总任务数
```

---

## 9. 部署

### 环境要求
- Python 3.12+
- uv（包管理器）

### 启动方式
```bash
# 安装依赖（首次）
uv sync

# 启动服务
PYTHONPATH=backend uv run uvicorn backend.main:app --host 0.0.0.0 --port 15000
```

### 端口
**15000**（可通过 `backend/config.py` 中的 `PORT` 修改）

### 数据库初始化
首次启动时自动建表、插入初始15条任务和2个用户。

---

## 10. 已知约束

- 小朋友（child）账号只能修改最近3天记录
- 家长（parent）账号可修改任意日期
- 每周汇总按 ISO week number 计算
- 日期格式：API 用 YYYY-MM-DD，显示用 MM/DD
- 时区：Asia/Shanghai
- 数据库文件 `data/habits.db` 不加入 Git
- `PYTHONPATH=backend` 是必须的（代码使用裸名导入）

---

## 11. 演示账号

| 角色 | 用户名 | 导码 |
|---|---|---|
| 家长 | tayhe | parents |
| 小朋友 | meow | child |

---

_Last updated: 2026-05-23 | v3.0_
