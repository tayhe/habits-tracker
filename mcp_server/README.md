# Habits Tracker MCP Server

通过 [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) 将 Habits Tracker（小鱼干·学习习惯追踪）与 AI Agent（如 Claude Desktop、Cursor、Antigravity 等）连接，支持 Agent 理解每日汇报并自动代行打卡。

---

## 提供的工具（Tools）

1. **`get_daily_records`**
   - **功能**：查询指定日期的任务列表（包含科目、任务名称、奖励金额）与打卡状态，以及今日完成统计和猫猫表情。
   - **参数**：`target_date`（格式 `YYYY-MM-DD`，可选，默认当天）。
2. **`check_in_habits`**
   - **功能**：批量更新任务打卡状态（勾选或取消勾选）。
   - **参数**：
     - `target_date`：日期（可选，默认当天）。
     - `completed_task_ids`：需要标记完成（打勾）的任务 ID 列表。
     - `uncompleted_task_ids`：需要取消勾选的任务 ID 列表（可选）。
   - **返回**：更新后的完成进度、猫猫表情及最新奖励。
3. **`get_weekly_summary`**
   - **功能**：获取目标周维度的各科任务达标进展与预计收益。
   - **参数**：`target_date`（可选，默认当天）。

---

## 运行与测试

本服务基于 Python 现代自包含脚本格式（PEP 723），只要安装了 `uv`，无需额外安装依赖即可直接运行：

```bash
# 启动 MCP 服务（stdio 协议）
uv run mcp_server/server.py
```

---

## 客户端配置示例

### 1. Claude Desktop 配置

在 Claude Desktop 配置文件中（macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`，Windows: `%APPDATA%\Claude\claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "habits-tracker": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/绝对路径/habits-tracker",
        "mcp_server/server.py"
      ],
      "env": {
        "HABITS_API_BASE": "http://127.0.0.1:15000",
        "HABITS_USERNAME": "meow",
        "HABITS_PASSWORD": "child"
      }
    }
  }
}
```

> **提示**：如果页面密码已在前端修改，可以直接提供 `HABITS_SESSION_TOKEN` 环境变量（有效期 30 天，可从浏览器 Cookie 中的 `session_token` 复制）。

### 2. Antigravity / Cursor 配置

在 MCP 配置中添加：

```json
{
  "habits-tracker": {
    "command": "uv",
    "args": [
      "run",
      "--directory",
      "/path/to/habits-tracker",
      "mcp_server/server.py"
    ],
    "env": {
      "HABITS_API_BASE": "http://127.0.0.1:15000",
      "HABITS_SESSION_TOKEN": "<your-session-token>"
    }
  }
}
```

---

## 环境变量参考

| 变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `HABITS_API_BASE` | `http://127.0.0.1:15000` | 后端服务 API 地址 |
| `HABITS_USERNAME` | `meow` | 自动登录的用户名（小朋友角色只能改最近 7 天，权限更安全） |
| `HABITS_PASSWORD` | `child` | 登录密码 |
| `HABITS_SESSION_TOKEN` | 空 | 若提供，将直接使用该 Cookie Token 跳过密码登录 |

---

## 典型自然语言交互示例

在支持 MCP 的 Agent 中直接输入：

- *“今天英语听力和课外阅读做完了，口算也完成了，字词还没写，帮我勾选一下打卡”*
- *“看看我今天还有哪些习惯没有完成？”*
- *“查看本周的学习达标情况和猫猫状态”*
