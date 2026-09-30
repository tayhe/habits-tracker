#!/usr/bin/env python3
"""Headless UI smoke: drive a real browser through every view and assert the wiring.

curl proves the API returns `subjects`; check_template_bindings.mjs proves the
template identifiers exist; pytest proves the backend contract. None of them
prove the browser actually renders. This script does:

  1. login through the real form;
  2. walk all five views and assert each container renders non-empty content
     (a broken view shows a silently blank screen, not an error);
  3. assert the trend table's subject columns and every task-management
     <select> come from GET /config (subjectList), not hardcoded text;
  4. assert seeded records actually surface as earnings in the trend table;
  5. assert zero console errors, zero page errors, zero >=400 responses;
  6. screenshot every view.

Run it against a live instance:

    scripts/ui_smoke.sh                              # isolated instance + this
    scripts/ui_smoke.py --base-url http://127.0.0.1:15000 --headed
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import APIRequestContext, Page, sync_playwright

API = "/api/v1"
SHANGHAI = ZoneInfo("Asia/Shanghai")
CREDS = {
    "username": os.environ.get("SMOKE_PARENT_USERNAME", "tayhe"),
    "password": os.environ.get("SMOKE_PARENT_PASSWORD", "parents"),
}

# (nav button label, view container selector)
VIEWS = [
    ("喵的雄心", "#ambitionView"),
    ("每日捕猎", "#dailyView"),
    ("一周战果", "#weeklyView"),
    ("征途", "#trendView"),
    ("军令状", "#taskMgmtView"),
]

# Columns the trend table always renders itself (not driven by /config).
FIXED_TREND_HEADERS = ["周", "总达标率", "趋势", "🐹 鼠鼠的总结", "最终收益", "爸爸兑现了吗"]

# GET /auth/me answers 401 before login by design (session restore probe).
ALLOWED_401 = ("/auth/me",)


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[bool, str]] = []

    def check(self, condition: bool, message: str) -> bool:
        self.rows.append((bool(condition), message))
        print(f"[{'ok' if condition else 'FAIL'}] {message}", flush=True)
        return bool(condition)

    def fail(self, message: str) -> None:
        self.check(False, message)

    @property
    def failures(self) -> list[str]:
        return [msg for ok, msg in self.rows if not ok]


def seed_records(req: APIRequestContext, rep: Report, task_count: int = 3) -> list[dict]:
    """Punch a few tasks across the previous week and this one.

    The previous week is fully in the past (parent may backdate); this week is
    clamped to today because future dates are rejected with 400.
    """
    login = req.post(f"{API}/auth/login", data=CREDS)
    if not rep.check(login.ok, f"API 登录 {CREDS['username']}"):
        return []

    config = req.get(f"{API}/config").json()
    subjects = config.get("subjects") or []
    rep.check(bool(subjects), f"/config 返回 subjects: {subjects}")

    tasks = req.get(f"{API}/tasks").json()
    picked = tasks[:task_count]
    rep.check(bool(picked), f"取到 {len(picked)}/{len(tasks)} 个任务用于播种")

    today = datetime.now(SHANGHAI).date()
    monday = today - timedelta(days=today.weekday())
    dates = [monday - timedelta(days=7) + timedelta(days=i) for i in range(7)]
    dates += [monday + timedelta(days=i) for i in range(today.weekday() + 1)]

    punched = 0
    for day in dates:
        for task in picked:
            resp = req.put(
                f"{API}/records",
                data={"date": day.isoformat(), "task_id": task["task_id"], "completed": True},
            )
            if not resp.ok:
                rep.fail(f"播种失败 {day} {task['task_id']} -> {resp.status}")
                return picked
            punched += 1
    rep.check(True, f"播种 {punched} 条打卡（{len(dates)} 天 × {len(picked)} 任务）")
    return picked


def wait_rendered(page: Page, selector: str, min_len: int = 20, timeout: int = 12000) -> None:
    page.wait_for_selector(selector, state="visible", timeout=timeout)
    page.wait_for_function(
        """([sel, minLen]) => {
            const el = document.querySelector(sel);
            return !!el && el.innerText.trim().length >= minLen;
        }""",
        arg=[selector, min_len],
        timeout=timeout,
    )


def last_token(text: str) -> str:
    parts = text.split()
    return parts[-1] if parts else ""


def walk_views(page: Page, shots: Path, rep: Report) -> None:
    for index, (label, selector) in enumerate(VIEWS, start=1):
        try:
            page.get_by_role("button", name=label, exact=True).click()
            wait_rendered(page, selector)
            if selector == "#trendView":
                page.wait_for_function(
                    "() => document.querySelectorAll('#trendView tbody tr').length >= 2",
                    timeout=12000,
                )
            rep.check(len(page.inner_text(selector).strip()) >= 20, f"{label} 渲染非空")
            page.screenshot(path=str(shots / f"{index}-{label}.png"), full_page=True)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            rep.fail(f"{label} 渲染失败：{str(exc).splitlines()[0]}")
            page.screenshot(path=str(shots / f"{index}-{label}-FAILED.png"), full_page=True)


def assert_subject_wiring(page: Page, request: APIRequestContext, rep: Report) -> None:
    """The two places this round changed: trend columns and the subject <select>."""
    subjects = request.get(f"{API}/config").json().get("subjects") or []
    if not rep.check(bool(subjects), f"subjectList 非空: {subjects}"):
        return

    headers = page.eval_on_selector_all(
        "#trendView thead th", "els => els.map(e => e.textContent.trim())"
    )
    got = [last_token(h) for h in headers if h not in FIXED_TREND_HEADERS]
    rep.check(got == subjects, f"征途表头学科列 = subjectList（期望 {subjects}，实际 {got}）")

    rows = page.locator("#trendView tbody tr").count()
    rep.check(rows >= 2, f"征途数据行 {rows} 行（播种后应 ≥2 周）")

    rewards = page.eval_on_selector_all(
        "#trendView tbody td.trend-reward", "els => els.map(e => parseFloat(e.textContent))"
    )
    funded = [r for r in rewards if r > 0]
    rep.check(
        len(funded) >= 2,
        f"征途有收益的周 = {len(funded)} 个（播种 2 周，全部值 {rewards}）",
    )

    task_rows = page.locator("#taskMgmtView .task-mgmt-row").count()
    rep.check(task_rows >= 2, f"军令状任务行 {task_rows} 行")
    options = page.eval_on_selector_all(
        "#taskMgmtView select", "sels => sels.map(s => [...s.options].map(o => o.value))"
    )
    if rep.check(bool(options), f"军令状科目下拉 {len(options)} 个"):
        bad = [o for o in options if o != subjects]
        rep.check(not bad, "军令状每行科目下拉 == subjectList" + ("" if not bad else f"（偏差 {bad[:1]}）"))


def finish(
    rep: Report,
    shots: Path,
    console_errors: list[str],
    page_errors: list[str],
    bad_responses: list[str],
    failed_requests: list[str],
) -> None:
    rep.check(not console_errors, f"console error = {len(console_errors)}")
    rep.check(not page_errors, f"pageerror = {len(page_errors)}")
    rep.check(not bad_responses, f"HTTP >=400 响应 = {len(bad_responses)}")
    rep.check(not failed_requests, f"请求失败 = {len(failed_requests)}")

    for name, items in (
        ("console error", console_errors),
        ("pageerror", page_errors),
        ("bad response", bad_responses),
        ("failed request", failed_requests),
    ):
        for item in items[:5]:
            print(f"       ↳ {name}: {item}", flush=True)

    print(f"\n截图: {shots}")
    if rep.failures:
        print(f"UI 冒烟失败 {len(rep.failures)} 项：")
        for msg in rep.failures:
            print(f"  - {msg}")
        sys.exit(1)
    print(f"UI 冒烟通过（{len(rep.rows)} 项断言）")


def run(base_url: str, shots: Path, headed: bool, rep: Report) -> None:
    shots.mkdir(parents=True, exist_ok=True)
    console_errors: list[str] = []
    page_errors: list[str] = []
    bad_responses: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as p:
        request = p.request.new_context(base_url=base_url, ignore_https_errors=True)
        seed_records(request, rep)

        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page(viewport={"width": 1440, "height": 960})

        def on_console(msg) -> None:
            if msg.type != "error":
                return
            loc = (msg.location or {}).get("url", "")
            if any(url in loc for url in ALLOWED_401):
                return
            console_errors.append(f"{msg.text} @ {loc or '(no location)'}")

        def on_response(resp) -> None:
            if resp.status < 400 or resp.url.endswith("/favicon.ico"):
                return
            if resp.status == 401 and any(url in resp.url for url in ALLOWED_401):
                return
            bad_responses.append(f"{resp.status} {resp.url}")

        def on_failed(req_) -> None:
            failure = req_.failure or ""
            if "ERR_ABORTED" in failure:
                return
            failed_requests.append(f"{req_.url} ({failure})")

        page.on("console", on_console)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("response", on_response)
        page.on("requestfailed", on_failed)

        # --- login through the real form -----------------------------------
        page.goto(base_url, wait_until="domcontentloaded")
        rep.check(page.locator("#loginPage").is_visible(), "登录页可见")
        page.fill('input[placeholder="用户名"]', CREDS["username"])
        page.fill('input[placeholder="密码"]', CREDS["password"])
        page.click('form.login-form button[type="submit"]')
        try:
            page.wait_for_selector("#app", state="visible", timeout=10000)
            rep.check(CREDS["username"] in page.inner_text("#header"), "UI 登录成功，头部用户名正确")
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            rep.fail(f"UI 登录失败：{str(exc).splitlines()[0]}")
            browser.close()
            request.dispose()
            finish(rep, shots, console_errors, page_errors, bad_responses, failed_requests)
            return

        walk_views(page, shots, rep)
        assert_subject_wiring(page, request, rep)

        browser.close()
        request.dispose()

    finish(rep, shots, console_errors, page_errors, bad_responses, failed_requests)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:15999")
    parser.add_argument("--shots", default="/tmp/opencode/ui-smoke-shots")
    parser.add_argument("--headed", action="store_true", help="run with a visible browser")
    args = parser.parse_args()
    run(args.base_url.rstrip("/"), Path(args.shots), args.headed, Report())


if __name__ == "__main__":
    main()
