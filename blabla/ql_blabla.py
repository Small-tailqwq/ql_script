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

    def get_posts(self, page_size: int = 10) -> list:
        res = self._req("POST", "/api/ugc/direct/standalonesite/Dynamics/GetPostList",
                        json={"page_index": 1, "page_size": page_size})
        if res.get("code") == 0:
            return res.get("data", {}).get("list", [])
        return []

    def browse_posts(self, posts: list, need: int) -> int:
        count = 0
        for p in posts[:need]:
            post_uuid = p.get("post_uuid")
            if not post_uuid:
                continue
            self._req("POST", "/api/ugc/direct/standalonesite/Dynamics/PostPicClickBrowse",
                      json={"post_uuid": post_uuid})
            count += 1
        return count

    def like_posts(self, posts: list, need: int) -> int:
        count = 0
        for p in posts[:need]:
            post_uuid = p.get("post_uuid")
            if not post_uuid:
                continue
            res = self._req("POST", "/api/ugc/proxy/standalonesite/Dynamics/PostStar",
                            json={"post_uuid": post_uuid, "status": 1})
            if res.get("code") == 0:
                count += 1
        return count

    def run(self) -> str:
        try:
            if not self.check_login():
                return "\n".join(self.messages)

            tasks = self.get_tasks()
            if not tasks:
                return "\n".join(self.messages)

            posts = None
            has_like = any(
                t.get("task_type") == 14
                and not all(r.get("is_completed", False) for r in t.get("reward_infos", []))
                for t in tasks
            )
            if has_like:
                posts = self.get_posts(10)

            for task in tasks:
                name = task.get("task_name", "")
                task_type = task.get("task_type")
                rewards = task.get("reward_infos", [])
                is_completed = all(r.get("is_completed", False) for r in rewards)

                if is_completed:
                    self._log(f"[{name}] 已完成")
                    continue

                if task_type == 1:
                    self.daily_checkin()
                elif task_type == 13:
                    self._log(f"[{name}] 浏览 API 已调但任务不更新，需调查")
                elif task_type == 14 and posts:
                    need = rewards[0].get("need_completed_times", 5)
                    done = self.like_posts(posts, need)
                    self._log(f"[{name}] 点赞贴文 ({done}/{need})")
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


def get_cookies() -> List[Dict[str, str]]:
    raw = os.environ.get("BLA_COOKIE", "").strip()
    if not raw:
        return []

    raw = raw.replace("&", "\n").replace(",", "\n")
    cookie_list = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("#", 1)
        cookie_val = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else f"账号{len(cookie_list) + 1}"
        if cookie_val:
            cookie_list.append({"cookie": cookie_val, "note": note})
    return cookie_list


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    cookies = get_cookies()
    if not cookies:
        logging.error("未找到 Cookie，请在环境变量中设置 'BLA_COOKIE'。")
        return

    logging.info(f"✅ 检测到 {len(cookies)} 个账号，开始执行 Blabla Link 每日签到...\n" + "-" * 30)

    notify_content = []
    all_success = True
    for cookie_data in cookies:
        signer = BlaSigner(cookie_data)
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
