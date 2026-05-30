# -*- coding: utf-8 -*-
"""
cron: 30 8 * * *
new Env('Blabla Link 每日签到');
"""

import hashlib
import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
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
CACHE_DIR = Path(os.environ.get("BLA_CACHE_DIR") or Path(__file__).parent / ".blabla_cache")

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
            done_key = hashlib.md5(self.cookie_str.encode()).hexdigest()[:16]
            done_file = CACHE_DIR / f"done_{done_key}.json"
            today = datetime.now().strftime("%Y-%m-%d")

            if done_file.exists():
                try:
                    done_data = json.loads(done_file.read_text(encoding="utf-8"))
                    if done_data.get("date") == today:
                        self._log("今日任务已全部完成，跳过")
                        return "\n".join(self.messages)
                except Exception:
                    pass

            if not self.check_login():
                return "\n".join(self.messages)

            tasks = self.get_tasks()
            if not tasks:
                return "\n".join(self.messages)

            all_completed = True

            for task in tasks:
                name = task.get("task_name", "")
                task_type = task.get("task_type")
                task_id = task.get("task_id")
                rewards = task.get("reward_infos", [])
                is_completed = all(r.get("is_completed", False) for r in rewards)

                if is_completed:
                    self._log(f"[{name}] 已完成")
                    continue

                all_completed = False

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

            self.redeem_rewards()

            self.total_points = self.get_total_points()
            self._log(f"当前总积分: {self.total_points}")

            if self.success and all_completed:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                done_file.write_text(json.dumps({"date": today}), encoding="utf-8")
        except Exception as e:
            self._log(f"执行异常: {str(e)}")
            self.success = False
        return "\n".join(self.messages)

    def get_role_info(self) -> dict:
        res = self._req("POST", "/api/game/proxy/Game/GetSavedRoleInfo", data="{}")
        if res.get("code") == 0:
            return res.get("data", {}).get("role_info", {})
        return {}

    def get_commodity_list(self) -> list:
        res = self._req("POST", "/api/lip/proxy/commodity/Commodity/GetUserCommodityList",
                        json={"page_num": 1, "page_size": 20, "game_id_list": ["29080"], "is_bind_lip": True})
        if res.get("code") == 0:
            return res.get("data", {}).get("commodity_list", [])
        return []

    def exchange_item(self, exchange_id: str, price: int, role_info: dict) -> tuple:
        body = {
            "exchange_commodity_id": exchange_id,
            "exchange_commodity_price": price,
            "role_info": {
                "area_id": role_info.get("area_id", ""),
                "game_id": role_info.get("game_id", "29080"),
                "game_name": role_info.get("game_name", "nikke_global"),
                "plat_id": role_info.get("plat_id", "0"),
                "role_id": role_info.get("role_id", ""),
                "role_name": role_info.get("role_name", ""),
                "zone_id": role_info.get("zone_id", "0"),
            },
            "save_role": False,
        }
        res = self._req("POST", "/api/lip/proxy/commodity/Commodity/ExchangeCommodity", json=body)
        code = res.get("code")
        return code == 0, code in (1100010,)

    def redeem_rewards(self):
        raw = os.environ.get("BLA_EXCHANGE", "").strip()
        if not raw:
            return
        targets = [x.strip() for x in raw.replace("，", ",").split(",") if x.strip()]

        cache_key = hashlib.md5(self.cookie_str.encode()).hexdigest()[:16]
        cache_file = CACHE_DIR / f"exchange_{cache_key}.json"
        this_month = datetime.now().strftime("%Y-%m")

        record = {}
        if cache_file.exists():
            try:
                record = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                record = {}

        commodity_list = self.get_commodity_list()
        if not commodity_list:
            self._log("获取商品列表失败，跳过兑换")
            return

        role_info = self.get_role_info()
        if not role_info:
            self._log("未找到角色信息，跳过兑换")
            return

        cid_map = {c["commodity_name"]: c for c in commodity_list}
        total_points = self.get_total_points()
        any_exchanged = False

        for target in targets:
            item = cid_map.get(target)
            if not item:
                self._log(f"未找到商品: {target}")
                continue

            if record.get(target) == this_month:
                self._log(f"[{target}] 本月已兑换，跳过")
                continue

            price = item["commodity_price"]
            if total_points < price:
                self._log(f"[{target}] 积分不足 ({total_points}<{price})，跳过")
                continue

            ok, limit_reached = self.exchange_item(item["exchange_commodity_id"], price, role_info)
            if ok or limit_reached:
                record[target] = this_month
                any_exchanged = True
            if ok:
                total_points -= price
                self._log(f"✅ 兑换成功: {target}")
            elif limit_reached:
                self._log(f"[{target}] 已达领取上限，跳过")
            else:
                self._log(f"❌ 兑换失败: {target}")

        if any_exchanged:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def check_cookie_valid(cookie: str) -> bool:
    try:
        resp = requests.post(f"{API_BASE}/api/user/CheckLogin",
                             data="{}",
                             headers={"Cookie": cookie, "Content-Type": "application/json"},
                             timeout=10)
        return resp.json().get("code") == 0
    except Exception:
        return False


def login_via_worker(email: str, password: str) -> str:
    key = hashlib.md5(email.encode()).hexdigest()[:16]
    cache_file = CACHE_DIR / key
    note = email.split("@")[0]

    if cache_file.exists():
        cookie = cache_file.read_text(encoding="utf-8").strip()
        if cookie and check_cookie_valid(cookie):
            logging.info(f"✅ [{note}] Cookie 缓存有效，跳过登录")
            return cookie
        logging.info(f"[{note}] Cookie 缓存已失效，重新登录")

    try:
        resp = requests.post(LOGIN_API, json={"email": email, "password": password}, timeout=TIMEOUT)
        data = resp.json()
        if data.get("code") == 0:
            cookie = data.get("data", {}).get("cookie", "")
            if cookie:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(cookie, encoding="utf-8")
                logging.info(f"✅ [{note}] Worker 登录成功，Cookie 已缓存")
                return cookie
        msg = data.get("message", "") or ""
        if "machine" in msg.lower() or "captcha" in msg.lower() or "验证" in msg or "滑块" in msg:
            logging.error(f"[{note}] 需要验证码，请手动获取 Cookie 后设置 BLA_COOKIE")
        else:
            logging.error(f"[{note}] Worker 登录失败: {msg}")
    except Exception as e:
        logging.error(f"[{note}] Worker 登录请求异常: {str(e)}")
    return ""


def get_credentials() -> List[Dict[str, str]]:
    cookies = []
    raw_cookie = os.environ.get("BLA_COOKIE", "").strip()
    raw_account = os.environ.get("BLA_ACCOUNT", "").strip()

    ck_list = []
    if raw_cookie:
        raw_cookie = raw_cookie.replace("\\n", "\n").replace("&", "\n").replace(",", "\n")
        for line in raw_cookie.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split("#", 1)
            cookie_val = parts[0].strip()
            note = parts[1].strip() if len(parts) > 1 else ""

            if len(parts) > 1 and "=" not in parts[0] and "=" in parts[1]:
                cookie_val, note = parts[1].strip(), parts[0].strip()

            if cookie_val:
                ck_list.append({"cookie": cookie_val, "note": note})

    if raw_account:
        raw_account = raw_account.replace("\\n", "\n").replace("&", "\n").replace(",", "\n")
        acc_lines = [l.strip() for l in raw_account.split("\n") if l.strip()]
        used_ck = set()

        for idx, line in enumerate(acc_lines):
            parts = line.split("#")
            email = parts[0].strip()
            password = parts[1].strip() if len(parts) > 1 else ""
            note = parts[2].strip() if len(parts) > 2 else f"账号{len(cookies) + 1}"
            if not email or not password:
                continue

            matched = None
            for ci, ck in enumerate(ck_list):
                if ci not in used_ck and ck["note"] == email:
                    matched = ck
                    used_ck.add(ci)
                    break

            if matched is None and idx < len(ck_list) and idx not in used_ck:
                matched = ck_list[idx]
                if "@" in matched["note"] and matched["note"] != email:
                    matched = None
                else:
                    used_ck.add(idx)

            if matched and check_cookie_valid(matched["cookie"]):
                key = hashlib.md5(email.encode()).hexdigest()[:16]
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                (CACHE_DIR / key).write_text(matched["cookie"], encoding="utf-8")
                cookies.append({"cookie": matched["cookie"], "note": note})
                logging.info(f"✅ [{email.split('@')[0]}] BLA_COOKIE 已缓存，跳过登录")
                continue

            logging.info(f"正在通过 Worker 登录: {email}")
            cookie = login_via_worker(email, password)
            if cookie:
                cookies.append({"cookie": cookie, "note": note})

    acct_count = len([l for l in raw_account.replace("&", "\n").replace(",", "\n").split("\n") if l.strip()]) if raw_account else 0
    for i in range(acct_count, len(ck_list)):
        if i not in used_ck:
            cookies.append({"cookie": ck_list[i]["cookie"], "note": ck_list[i]["note"] or f"账号{len(cookies) + 1}"})

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
