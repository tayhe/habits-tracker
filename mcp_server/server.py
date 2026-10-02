# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.28.1",
#     "mcp>=1.3.0",
# ]
# ///
"""Habits Tracker MCP Server.

Provides tools for AI Agents to inspect daily habits, update check-in status,
and query weekly progress via the Habits Tracker HTTP API.
"""

import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

# Support both mcp 2.x (MCPServer) and mcp 1.x (FastMCP)
# ToolError marks a failure we anticipated: the MCP SDK forwards its message to
# the caller, instead of masking it as a generic "Error executing tool <name>".
try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer
    from mcp.server.fastmcp.exceptions import ToolError

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

API_BASE = os.getenv("HABITS_API_BASE", "http://127.0.0.1:15000").rstrip("/")
USERNAME = os.getenv("HABITS_USERNAME", "meow")
PASSWORD = os.getenv("HABITS_PASSWORD", "child")
SESSION_TOKEN = os.getenv("HABITS_SESSION_TOKEN", "")


class AuthRejected(ToolError):
    """The backend refused the configured credentials (HTTP 401 on login).

    Kept distinct from other tool errors because no retry can clear it: the
    caller latches the message so a misconfigured deployment stops spending
    login attempts, which the rate limiter counts against the web UI sharing
    this host.
    """


class HabitsClient:
    """HTTP client wrapper managing authentication and requests to Habits Tracker."""

    def __init__(self, base_url: str, username: str, password: str, session_token: str = ""):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session_token = session_token
        self._client = httpx.Client(base_url=self.base_url, timeout=15.0)
        if self.session_token:
            self._client.cookies.set("session_token", self.session_token)
        # Latched after a login is definitively refused. Credentials reach this
        # process through the environment, so they can only change by starting a
        # new process; there is nothing to gain by re-asking.
        self._auth_error: str | None = None

    def login(self) -> None:
        """Authenticate with the server and store session cookie.

        Raises AuthRejected when the backend refuses the credentials, and
        ToolError for transient failures such as 429 or 5xx.
        """
        try:
            resp = self._client.post(
                "/api/v1/auth/login",
                json={"username": self.username, "password": self.password},
            )
            if resp.status_code != 200:
                detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type") == "application/json" else resp.text
                # 401 means these credentials are wrong, which no retry repairs.
                # 429 and 5xx are transient, so they stay ordinary ToolErrors.
                kind = AuthRejected if resp.status_code == 401 else ToolError
                raise kind(f"Habits Tracker 登录失败 [{resp.status_code}]: {detail}")
            # Cookie is stored automatically in self._client.cookies
        except httpx.ConnectError as err:
            raise ToolError(
                f"无法连接到 Habits Tracker 后端 ({self.base_url})，请确认服务已启动。"
            ) from err

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send authenticated request, retrying login once if session expired."""
        if self._auth_error is not None:
            # Already refused once: report it without spending another attempt.
            raise ToolError(self._auth_error)
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as err:
            raise ToolError(
                f"无法连接到 Habits Tracker 后端 ({self.base_url})，请确认服务已启动。"
            ) from err

        if resp.status_code == 401 and self.username and self.password:
            # A 401 here is ambiguous: the session cookie may have expired (the
            # backend purges sessions nightly), or the credentials may be wrong.
            # Ask for exactly one fresh login to tell those apart, and retry only
            # when it succeeds. A refused login means every later call would
            # refuse too, so latch it and fail without touching the network --
            # otherwise repeated use walks into the rate limiter and locks out
            # the web UI on this same host.
            try:
                self.login()
            except AuthRejected as err:
                self._auth_error = str(err)
                raise ToolError(self._auth_error) from err
            resp = self._client.request(method, path, **kwargs)

        if resp.status_code >= 400:
            err_msg = resp.text
            try:
                err_data = resp.json()
                if "detail" in err_data:
                    err_msg = str(err_data["detail"])
            except Exception:
                pass
            raise ToolError(f"接口调用失败 [{resp.status_code}]: {err_msg}")

        return resp


habits_client = HabitsClient(API_BASE, USERNAME, PASSWORD, SESSION_TOKEN)

# Initialize MCP Server
app = MCPServer(
    name="habits-tracker",
    instructions=(
        "Habits Tracker 助手服务。\n"
        "你可以通过工具查询用户的学习打卡习惯列表、各任务完成状态，并根据用户自然语言汇报帮忙勾选或取消打卡。\n"
        "通常流程：\n"
        "1. 当用户汇报每日学习情况时，先调用 get_daily_records 获取今日任务列表（包含科目与名称）；\n"
        "2. 将用户的话与任务名称/科目进行语义对齐匹配出 task_id；\n"
        "3. 调用 check_in_habits 提交勾选，并向用户反馈最新的完成统计、累计收益与猫猫表情。"
    ),
)


def _get_effective_date(target_date: str) -> str:
    """Return stripped target_date or current date in Asia/Shanghai timezone."""
    d = target_date.strip() if target_date else ""
    if not d:
        return datetime.now(SHANGHAI_TZ).date().isoformat()
    return d


@app.tool()
def get_daily_records(target_date: str = "") -> dict:
    """获取指定日期的学习习惯任务列表及完成情况。

    参数:
        target_date: 目标日期（格式 YYYY-MM-DD，为空则默认为今日）

    返回:
        包含日期、完成数、总数、猫猫表情、总收益，以及各项任务的具体详情（task_id, task_name, subject, reward, completed）。
    """
    effective_date = _get_effective_date(target_date)
    resp = habits_client.request("GET", "/api/v1/records", params={"date": effective_date})
    data = resp.json()
    return {
        "date": data.get("date"),
        "completed_count": data.get("completed_count", 0),
        "total_count": data.get("total_count", 0),
        "emoji": data.get("emoji", "😿"),
        "total_reward": data.get("total_reward", 0.0),
        "records": [
            {
                "task_id": r["task_id"],
                "subject": r["subject"],
                "task_name": r["task_name"],
                "reward": r["reward"],
                "completed": r["completed"],
            }
            for r in data.get("records", [])
        ],
    }


@app.tool()
def check_in_habits(
    target_date: str = "",
    completed_task_ids: list[str] | None = None,
    uncompleted_task_ids: list[str] | None = None,
) -> dict:
    """批量更新指定日期的打卡状态。

    参数:
        target_date: 打卡日期（格式 YYYY-MM-DD，为空则默认为今日）
        completed_task_ids: 需要标记为“已完成（勾选）”的任务 ID 列表
        uncompleted_task_ids: 需要标记为“未完成（取消勾选）”的任务 ID 列表（可选）

    返回:
        更新结果及该日期最新的完成进度与猫猫表情。
    """
    effective_date = _get_effective_date(target_date)
    updates = []
    for tid in completed_task_ids or []:
        updates.append({"date": effective_date, "task_id": tid, "completed": True})
    for tid in uncompleted_task_ids or []:
        updates.append({"date": effective_date, "task_id": tid, "completed": False})

    if not updates:
        return {"message": "没有提供需要更新的任务 ID", "updated_count": 0}

    # Execute batch update
    habits_client.request("PUT", "/api/v1/records/batch", json=updates)

    # Re-fetch latest status for immediate feedback
    latest = get_daily_records(effective_date)
    return {
        "message": f"成功更新 {len(updates)} 项任务打卡记录",
        "date": effective_date,
        "completed_count": latest["completed_count"],
        "total_count": latest["total_count"],
        "emoji": latest["emoji"],
        "total_reward": latest["total_reward"],
        "records": latest["records"],
    }


@app.tool()
def get_weekly_summary(target_date: str = "") -> dict:
    """获取目标日期所在周的学习习惯汇总统计。

    参数:
        target_date: 目标日期（格式 YYYY-MM-DD，为空则默认为今日）

    返回:
        周信息、达标天数、预计收益以及各个任务在本周的达标情况（每周最低要求与实际完成次数）。
    """
    effective_date = _get_effective_date(target_date)
    resp = habits_client.request("GET", "/api/v1/records/week", params={"date": effective_date})
    data = resp.json()
    return {
        "week": data.get("week"),
        "week_start": data.get("week_start"),
        "week_end": data.get("week_end"),
        "expected_earn": data.get("expected_earn", 0.0),
        "week_completed_days": data.get("week_completed_days", 0),
        "task_progress": [
            {
                "task_id": tp["task_id"],
                "name": tp["name"],
                "subject": tp["subject"],
                "weekly_min": tp["weekly_min"],
                "completed_count": tp["completed_count"],
                "qualified": tp["qualified"],
                "reward": tp["reward"],
            }
            for tp in data.get("task_progress", [])
        ],
    }


if __name__ == "__main__":
    app.run()
