# -*- coding: utf-8 -*-
"""
调试版本 - 硬编码 Cookie
"""

import logging
import os
import random
import time
from typing import Dict, List
import requests

TIMEOUT = 30
API_BASE = "https://api.blablalink.com"

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
    def __init__(self, cookie_str: str):
        self.cookie_str = cookie_str
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.messages = []
        self.success = True
        self.total_points = 0

    def _log(self, msg: str):
        logging.info(f"[DEBUG] {msg}")
        self.messages.append(msg)

    def _req(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Cookie", self.cookie_str)
        try:
            resp = self.session.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
            data = resp.json()
            print(f"[API] {method} {path} -> {resp.status_code} | code={data.get('code')} msg={data.get('msg')}")
            return data
        except Exception as e:
            print(f"[API] {method} {path} -> 异常: {e}")
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
        res = self._req("GET", "/api/lip/proxy/lipass/Points/GetTaskListWithStatusV2",
                        params={"get_top": "false", "intl_game_id": "29080"})
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
                delay = random.uniform(min_delay, max_delay)
                print(f"  等待 {delay:.1f} 秒...")
                time.sleep(delay)
        return count

    def run(self):
        if not self.check_login():
            return

        tasks = self.get_tasks()
        if not tasks:
            return

        print("\n--- 任务列表 ---")
        for t in tasks:
            name = t.get("task_name", "")
            task_type = t.get("task_type")
            rewards = t.get("reward_infos", [])
            done = rewards[0].get("is_completed", False) if rewards else False
            pts = rewards[0].get("points", 0) if rewards else 0
            status = "✅" if done else "⏳"
            print(f"  {status} [{task_type}] {name} ({pts}pts)")

        print("\n--- 执行任务 ---")

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

        print("\n--- 执行结果 ---")
        for m in self.messages:
            print(f"  {m}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    cookie = (
        "game_channelid=131; "
        "game_token=ce869d6f6c0e4ec6caaa12803fb2f68001e1eeb1; "
        "game_gameid=29080; "
        "game_login_game=0; "
        "game_openid=13161285947484504729; "
        "game_user_name=Ko_teiru; "
        "game_uid=3447419455688161; "
        "game_adult_status=1"
    )

    print("=" * 50)
    print("Blabla Link 每日签到 - 调试模式")
    print("=" * 50)

    signer = BlaSigner(cookie)
    signer.run()

    print("\n" + "=" * 50)
    print("调试完成")


if __name__ == "__main__":
    main()
