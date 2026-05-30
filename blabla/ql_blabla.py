# -*- coding: utf-8 -*-
"""
cron: 30 8 * * *
new Env('Blabla Link 每日签到');
"""

import json
import logging
import os
import random
import time
from typing import Dict, List
import requests
import re

try:
    from sendNotify import send
except Exception:
    try:
        from notify import send
    except Exception:
        send = None

TIMEOUT = 30
API_BASE = "https://api.blablalink.com"
LOGIN_API = "https://nikke-cdk-test.hayasa.org/api/login"

HEADERS = {
    "x-channel-type": "2",
    "x-language": "zh-TW",
    "x-common-params": '{"game_id":"16","area_id":"global","source":"pc_web","intl_game_id":"29080","language":"zh-TW","env":"prod"}',
    "Origin": "https://www.blablalink.com",
    "Referer": "https://www.blablalink.com/",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


class BlaSigner:
    def __init__(self, cookie_data: Dict[str, str]):
        self.cookie_str = cookie_data["cookie"]
        self.note = cookie_data.get("note", "未命名账号")
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.messages = []
        self.success = True
        self.total_points = 0

    def _log(self, msg: str):
        logging.info(f"[{self.note}] {msg}")
        self.messages.append(msg)

    def _req(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Cookie", self.cookie_str)
        try:
            resp = self.session.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
            return resp.json()
        except Exception as e:
            return {"code": -1, "msg": f"请求异常: {str(e)}"}

    def check_login(self) -> bool:
        res = self._req("POST", "/api/user/CheckLogin", data="{}")
        if res.get("code") != 0:
            self._log(f"Cookie 已失效: {res.get('msg')}")
            self.success = False
            return False
        self._log("Cookie 有效")
        return True

    def get_tasks(self) -> list:
        res = self._req("GET", "/api/lip/proxy/lipass/Points/GetTaskListWithStatusV2", params={"get_top": "false", "intl_game_id": "29080"})
        if res.get("code") != 0:
            self._log(f"获取任务列表失败: {res.get('msg')}")
            self.success = False
            return []
        return res.get("data", {}).get("tasks", [])

    def daily_checkin(self) -> bool:
        res = self._req("POST", "/api/lip/proxy/lipass/Points/DailyCheckIn", json={"task_id": "15"})
        if res.get("code") == 0:
            self._log("每日签到成功 ✓")
            return True
        elif "already" in str(res.get("msg", "")).lower() or "重复" in str(res.get("msg", "")):
            self._log("今日已签到")
            return True
        else:
            self._log(f"签到失败: {res.get('msg')}")
            return False

    def get_total_points(self) -> int:
        res = self._req("GET", "/api/lip/proxy/lipass/Points/GetUserTotalPoints")
        if res.get("code") == 0:
            return res.get("data", {}).get("total_points", 0)
        return 0

    def complete_task(self, task_id: str, need: int, min_delay: float = 1.0, max_delay: float = 3.0) -> int:
        count = 0
        for i in range(need):
            res = self._req("POST", "/api/lip/proxy/lipass/Points/CompleteTaskAddPoint",
                            json={"task_id": task_id, "intl_game_id": "29080"})
            if res.get("code") == 0:
                count += 1
            if i < need - 1:
                time.sleep(random.uniform(min_delay, max_delay))
        return count

    def run(self) -> str:
        try:
            if not self.check_login():
                return "\n".join(self.messages)

            tasks = self.get_tasks()
            if not tasks:
                return "\n".join(self.messages)

            for task in tasks:
                name = task.get("task_name", "")
                task_type = task.get("task_type")
                task_id = task.get("task_id")
                rewards = task.get("reward_infos", [])
                is_completed = all(r.get("is_completed", False) for r in rewards)

                if is_completed:
                    self._log(f"[{name}] 已完成")
                    continue

                if task_type == 1:
                    self.daily_checkin()
                elif task_type in (13, 14) and task_id:
                    need = rewards[0].get("need_completed_times", 5)
                    done = self.complete_task(task_id, need)
                    self._log(f"[{name}] ({done}/{need})")
                elif task_type == 2:
                    self._log(f"[{name}] 需游戏内完成，跳过")
                else:
                    self._log(f"[{name}] 未知任务类型，跳过")

            self.total_points = self.get_total_points()
            self._log(f"当前总积分: {self.total_points}")
        except Exception as e:
            self._log(f"执行异常: {str(e)}")
            self.success = False
        return "\n".join(self.messages)


def login_via_worker(email: str, password: str) -> str:
    try:
        resp = requests.post(LOGIN_API, json={"email": email, "password": password}, timeout=TIMEOUT)
        data = resp.json()
        if data.get("code") == 0:
            cookie = data.get("data", {}).get("cookie", "")
            if cookie:
                logging.info(f"✅ Worker 登录成功: {data['data'].get('userName', '')}")
                return cookie
        logging.error(f"Worker 登录失败: {data.get('message', '未知错误')}")
    except Exception as e:
        logging.error(f"Worker 登录请求异常: {str(e)}")
    return ""


def get_credentials() -> List[Dict[str, str]]:
    cookies = []
    raw_cookie = os.environ.get("BLA_COOKIE", "").strip()
    raw_account = os.environ.get("BLA_ACCOUNT", "").strip()

    if raw_cookie:
        raw_cookie = raw_cookie.replace("&", "\n").replace(",", "\n")
        for line in raw_cookie.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("#", 1)
            cookie_val = parts[0].strip()
            note = parts[1].strip() if len(parts) > 1 else f"账号{len(cookies) + 1}"
            if cookie_val:
                cookies.append({"cookie": cookie_val, "note": note})

    if raw_account:
        raw_account = raw_account.replace("&", "\n").replace(",", "\n")
        for line in raw_account.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("#")
            email = parts[0].strip()
            password = parts[1].strip() if len(parts) > 1 else ""
            note = parts[2].strip() if len(parts) > 2 else f"账号{len(cookies) + 1}"
            if email and password:
                logging.info(f"正在通过 Worker 登录: {email}")
                cookie = login_via_worker(email, password)
                if cookie:
                    cookies.append({"cookie": cookie, "note": note})

    return cookies


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    credentials = get_credentials()
    if not credentials:
        logging.error("未找到凭证，请设置环境变量 'BLA_COOKIE' 或 'BLA_ACCOUNT'（邮箱#密码）。")
        return

    logging.info(f"✅ 检测到 {len(credentials)} 个账号，开始执行 Blabla Link 每日签到...\n" + "-" * 30)

    notify_content = []
    all_success = True
    for cred in credentials:
        signer = BlaSigner(cred)
        result_msg = signer.run()
        status_icon = "✅" if signer.success else "❌"
        if not signer.success:
            all_success = False
        header = f"【{signer.note}】{status_icon}"
        notify_content.append(header)
        notify_content.append(result_msg)
        notify_content.append("-" * 20)

    final_content = "\n".join(notify_content)
    logging.info(f"\n{final_content}")

    if send:
        send("Blabla Link 每日签到", final_content)


if __name__ == "__main__":
    main()
