# Habits_Tracker 项目规范

## 1. 项目概述

### 背景
- 原系统：Notion 上的"小鱼干学习习惯追踪系统"（Notion 模板）
- 问题：WPS 多维表格实现效果未达预期，暂停
- 新方案：HTML 单页应用 + Python FastAPI 后端

### 目标
- 完美复刻 Notion Habits_Tracker 的产品体验
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
projects/Habits_Tracker/
├── AGENT.md                 # 本规范文档
├── backend/
│   ├── main.py              # FastAPI 入口、路由定义
│   ├── models.py            # Pydantic 数据模型
│   ├── database.py          # SQLite 连接与初始化
│   ├── auth.py              # 鉴权逻辑（parent/child）
│   ├── routers/
│   │   ├── tasks.py         # 任务定义 CRUD
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
| GET | /records?date=YYYY-MM-DD | 获取指定日期各任务完成情况 | 登录用户 |
| PUT | /records | 批量更新某日各任务完成状态 | 登录用户（child 仅限最近3天） |
| GET | /records/range?start=DATE&end=DATE | 获取日期范围内记录 | 登录用户 |

### 汇总
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| GET | /summary/daily?date=YYYY-MM-DD | 每日汇总（含表情符号） | 登录用户 |
| GET | /summary/weekly?week=YYYY-WXX | 每周汇总（按科目） | 登录用户 |

### 导入
| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | /import/csv | 导入历史 CSV 数据 | parent |

---

## 5. 前端设计

### 页面结构
```
┌─────────────────────────────────────────┐
│ Header: Logo + 用户名 + 登出            │
├─────────────────────────────────────────┤
│ 视图切换: [每日追踪] [每周汇总] [任务管理]│  （家长可见任务管理）
├─────────────────────────────────────────┤
│                                         │
│  主内容区（根据视图切换）                │
│                                         │
└─────────────────────────────────────────┘
```

### 每日追踪视图
- 顶部：日期选择器（< 今天 >）或**七日视图**（见下方说明）
- 主体：按科目分组，每科下各任务子项以**彩色标签（Tag）**形式展示
- 每个子项格子：**未完成**显示为空/灰色；**已完成**显示为彩色圆角标签（参考 Notion 风格）
- 点击格子弹出**多选下拉菜单**（预设该科所有子项），已选的打勾显示在格子里
- 底部：本日总收益 + 完成进度表情（🐟🐡/🐟/😭）

**七日视图（小朋友界面专用）：**
- 水平滚动展示最近7天（今天在右侧）
- **最近3天**的完成次数格子可编辑（绿色高亮边框）
- **第4~7天**为只读展示（灰色背景，hover 显示"历史记录不可修改"）
- 日期列底部显示当日进度表情和总收益

### 每周汇总视图
- 顶部：周次选择器
- 主体：按科目分栏，每科显示本周完成率、完成天数、总收益
- 底部：全科总收益

### 任务管理视图（仅家长）
- 任务列表（可编辑/删除）
- 新增任务表单

### Notion 风格还原要点
- emoji 表情作为进度符号（🐟🐡 = 超额完成，🐟 = 完成，😭 = 未达标）
- 卡片式布局，分组清晰
- 字体、间距、圆角还原 Notion 质感
- 响应式：小屏幕设备也能用

---

## 6. 认证与权限矩阵

| 操作 | parent | child |
|---|---|---|
| 登录 | ✅ | ✅ |
| 查看所有视图 | ✅ | ✅（无任务管理） |
| 填写完成次数 | ✅（任意日期） | ✅（最近3天可编辑） |
| 管理任务定义 | ✅ | ❌ |
| 导入历史数据 | ✅ | ❌ |

---

## 5. 小朋友界面七日视图（补充说明）

**每日追踪标签下显示最近7天，水平排列7列：**
- 今天在最右侧（第7列）
- 最近3天（第5~7列）：完成次数格子可编辑，绿色边框
- 第1~4列（更早的历史）：灰色背景，只读，hover 显示「历史记录不可修改」
- 每列底部：该日进度表情 + 该日总收益

**家长界面**：维持原有的单日切换模式（◀ 某日 ▶），但也支持切换到七日总览模式

---

---

## 7. 表情计算规则

```python
def progress_emoji(completed_tasks: int, total_tasks: int, weekly_min: int) -> str:
    """
    单日完成率 = completed_tasks / total_tasks
    但实际表情判断需参考本周该科目的完成情况：
    
    单科表情（单日）：
    - 该科今日完成任务数 / 该科总任务数 ≥ 50% → 🐟
    - 该科今日完成任务数 / 该科总任务数 ≥ 100% → 🐟🐡
    - 否则 → 😭
    
    本日总表情（汇总英语+数学+语文）：
    - 三科均 ≥ 100% → 🐟🐡
    - 三科均 ≥ 50% → 🐟
    - 其他情况 → 😭（参考当日总收益是否达标）
    """
```

**注意**：由于子项只有完成/未完成两种状态（布尔值），不涉及数字计数。每日进度表情由当日各科完成率决定，而非完成次数。

---

## 8. 部署方案

### 启动方式（局域网）
```bash
cd projects/Habits_Tracker/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 18765
```

访问地址：`http://<服务器IP>:18765`

### 数据库初始化
首次启动时自动建表、插入初始15条任务。

### 端口
使用 **18765**（与现有服务不冲突）

---

## 9. 实现阶段

### Phase 1：后端骨架 ✅ 规划
- [ ] 项目目录创建
- [ ] FastAPI 骨架（含 CORS 配置）
- [ ] SQLite 数据库初始化
- [ ] User / Task 模型
- [ ] 登录认证接口

### Phase 2：核心 API
- [ ] Tasks CRUD
- [ ] DailyRecords 读写
- [ ] DailySummary / WeeklySummary
- [ ] CSV 导入

### Phase 3：前端
- [ ] HTML + CSS 框架（复刻 Notion 风格）
- [ ] 每日追踪视图
- [ ] 每周汇总视图
- [ ] 任务管理视图
- [ ] 登录页

### Phase 4：测试与数据迁移
- [ ] 历史数据从 Notion CSV 导入
- [ ] 功能测试
- [ ] 局域网访问验证

---

## 10. 已知约束与注意事项

- 小朋友（child）账号只能修改最近3天记录，不能修改更早历史
- 每周汇总按周次（ISO week number）计算
- 日期使用 YYYY-MM-DD 格式
- 所有时间使用 Asia/Shanghai 时区
- 数据库文件 `data/habits.db` 不加入 Git

---

_Last updated: 2026-05-21_