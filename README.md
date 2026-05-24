# 小鱼干·学习习惯追踪

一个帮助小朋友追踪每日学习习惯完成情况的 Web 应用。源自 Notion 模板，使用纯 HTML + FastAPI 构建，支持局域网多设备访问。

## 功能

- **每日追踪**：以 Notion 风格表格展示一周 7 天的任务完成情况，支持点击切换完成状态
- **每周汇总**：按科目统计达标项目数和收益，激励小朋友坚持完成学习任务
- **双角色系统**：家长可管理任务和查看全部数据，小朋友可填写最近 3 天的完成情况
- **收益机制**：每个任务有单次预估收益和周最低完成次数，达标后按实际完成次数计入真实收益
- **多设备访问**：支持局域网内任意浏览器访问

## 安装方式

### 方式一：本地安装（推荐开发）

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone <仓库地址>
cd habits-tracker

# 安装依赖
uv sync

# 启动服务
PYTHONPATH=backend uv run uvicorn backend.main:app --host 0.0.0.0 --port 15000
```

访问 http://localhost:15000

### 方式二：Docker

需要 Docker 和 Docker Compose。

```bash
git clone <仓库地址>
cd habits-tracker

# 一键启动
docker compose up -d
```

访问 http://localhost:15000

数据自动持久化到 `./data` 目录。

## 演示账号

| 角色 | 用户名 | 密码 |
|------|--------|------|
| 家长 | tayhe | parents |
| 小朋友 | meow | child |

## 技术栈

- 后端：Python 3 + FastAPI
- 数据库：SQLite
- 前端：纯 HTML + CSS + JavaScript（单文件）
- 包管理：uv
- 容器化：Docker

## 项目结构

```
habits-tracker/
├── backend/          # FastAPI 后端
│   ├── main.py       # 入口、路由注册
│   ├── config.py     # 配置（端口、数据库路径等）
│   ├── models.py     # Pydantic 数据模型
│   ├── database.py   # SQLite 连接与初始化
│   ├── auth.py       # 认证逻辑
│   └── routers/      # API 路由
├── frontend/
│   └── index.html    # 单页应用
├── data/             # SQLite 数据库（自动创建，已 gitignore）
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml    # 项目依赖
```

## 许可证

私有项目
