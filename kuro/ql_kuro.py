# -*- coding: utf-8 -*-
"""
cron: 30 8 * * *
new Env('库街区自动签到');
"""

import datetime
import json
import logging
import os
import random
import time
import uuid
from typing import Dict, List, Optional
import requests

# 尝试导入青龙通知
try:
    from sendNotify import send  # type: ignore
except Exception:
    try:
        from notify import send  # type: ignore
    except Exception:
        send = None

# ================= 配置常量 =================
TIMEOUT = 30
GAME_WUWA_ID = "3"
GAME_PGR_ID = "2"
SERVER_WUWA = "76402e5b20be2c39f095a152090afddc"
SERVER_PGR = "1000"

class API:
    USER_MINE = "https://api.kurobbs.com/user/mineV2"
    USER_SIGN_IN = "https://api.kurobbs.com/user/signIn"
    USER_ROLE_LIST = "https://api.kurobbs.com/user/role/findRoleList"
    FORUM_LIST = "https://api.kurobbs.com/forum/list"
    FORUM_POST_DETAIL = "https://api.kurobbs.com/forum/getPostDetail"
    FORUM_LIKE = "https://api.kurobbs.com/forum/like"
    TASK_PROCESS = "https://api.kurobbs.com/encourage/level/getTaskProcess"
    TASK_SHARE = "https://api.kurobbs.com/encourage/level/shareTask"
    GAME_SIGN_IN = "https://api.kurobbs.com/encourage/signIn/v2"

# ================= 核心业务逻辑 =================
class KuroSigner:
    def __init__(self, token_data: Dict[str, str]):
        self.token = token_data['token']
        self.note = token_data.get('note', '未命名账号')
        
        # 模拟设备信息
        self.ip = "10.0.2.233"
        self.devcode = str(uuid.uuid4())
        self.distinct_id = str(uuid.uuid4())
        
        self.session = requests.Session()
        self.user_id = None
        self.wuwa_role_id = None
        self.pgr_role_id = None
        self.messages = []
        self.success = True

    def _log(self, msg: str):
        logging.info(f"[{self.note}] {msg}")
        self.messages.append(msg)

    def _req(self, url: str, method: str = 'POST', data: dict = None, req_type: str = 'bbs') -> dict:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Host": "api.kurobbs.com",
            "source": "ios",
        }

        if req_type == 'bbs':
            headers.update({
                "lang": "zh-Hans",
                "User-Agent": "KuroGameBox/48 CFNetwork/1492.0.1 Darwin/23.3.0",
                "channelId": "1",
                "channel": "appstore",
                "version": "2.2.0",
                "model": "iPhone15,2",
                "osVersion": "17.3",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "Cookie": f"user_token={self.token}",
                "Ip": self.ip,
                "distinct_id": self.distinct_id,
                "devCode": self.devcode,
                "token": self.token,
            })
        elif req_type == 'game':
            headers.update({
                "Accept": "application/json, text/plain, */*",
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "cors",
                "Origin": "https://web-static.kurobbs.com",
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/2.2.0",
                "devCode": f"{self.ip}, Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) KuroGameBox/2.2.0",
                "token": self.token,
            })
        elif req_type == 'user_info':
            headers.update({
                "osversion": "Android",
                "countrycode": "CN",
                "ip": self.ip,
                "model": "2211133C",
                "source": "android",
                "lang": "zh-Hans",
                "version": "1.0.9",
                "versioncode": "1090",
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": "okhttp/3.10.0",
                "devcode": self.devcode,
                "distinct_id": self.distinct_id,
                "token": self.token,
            })

        try:
            if method == 'POST':
                resp = self.session.post(url, headers=headers, data=data, timeout=TIMEOUT).json()
            else:
                resp = self.session.get(url, headers=headers, timeout=TIMEOUT).json()
            return resp
        except Exception as e:
            return {"code": -1, "msg": f"请求异常: {str(e)}"}

    def init_user_data(self) -> bool:
        """获取账号基础信息（userId、各游戏角色ID）"""
        # 获取 User ID
        res = self._req(API.USER_MINE, req_type='user_info')
        if res.get('code') != 200:
            self._log(f"获取用户信息失败或Token已过期: {res.get('msg')}")
            self.success = False
            return False
        self.user_id = res['data']['mine']['userId']
        
        # 获取鸣潮角色ID
        res_wuwa = self._req(API.USER_ROLE_LIST, data={"gameId": GAME_WUWA_ID}, req_type='user_info')
        if res_wuwa.get('code') == 200 and res_wuwa.get('data'):
            self.wuwa_role_id = res_wuwa['data'][0].get('roleId')
            
        # 获取战双角色ID
        res_pgr = self._req(API.USER_ROLE_LIST, data={"gameId": GAME_PGR_ID}, req_type='user_info')
        if res_pgr.get('code') == 200 and res_pgr.get('data'):
            self.pgr_role_id = res_pgr['data'][0].get('roleId')
            
        return True

    def game_sign(self):
        """游戏福利签到"""
        month = datetime.datetime.now().strftime("%m")
        
        def _do_sign(game_name, game_id, server_id, role_id):
            if not role_id:
                return
            data = {
                "gameId": game_id,
                "serverId": server_id,
                "roleId": role_id,
                "userId": self.user_id,
                "reqMonth": month,
            }
            res = self._req(API.GAME_SIGN_IN, data=data, req_type='game')
            if res.get('code') == 200:
                self._log(f"[{game_name}] 签到成功！")
            elif res.get('code') == 1511:
                self._log(f"[{game_name}] 今日已签到。")
            else:
                self._log(f"[{game_name}] 签到失败: {res.get('msg')}")

        _do_sign("鸣潮", GAME_WUWA_ID, SERVER_WUWA, self.wuwa_role_id)
        time.sleep(1)
        _do_sign("战双", GAME_PGR_ID, SERVER_PGR, self.pgr_role_id)

    def forum_tasks(self):
        """论坛每日活跃任务"""
        # 1. 论坛签到
        res = self._req(API.USER_SIGN_IN, data={"gameId": "2"}, req_type='bbs')
        if res.get('code') == 200:
            self._log("论坛签到成功")
        elif res.get('code') == 1511:
            pass # 已签到
            
        time.sleep(1)
        
        # 2. 获取任务状态
        res_tasks = self._req(API.TASK_PROCESS, data={"gameId": "0"}, req_type='bbs')
        if res_tasks.get('code') != 200:
            self._log("获取每日任务列表失败跳过")
            return
            
        tasks = res_tasks.get('data', {}).get('dailyTask', [])
        tasks_map = {t.get('remark'): t.get('process') for t in tasks}
        
        # 提前获取一波帖子列表备用（浏览、点赞需要）
        posts = []
        if tasks_map.get("浏览3篇帖子", 1) == 0 or tasks_map.get("点赞5次", 1) == 0:
            res_posts = self._req(API.FORUM_LIST, data={"forumId": "9", "gameId": "3", "pageIndex": "1", "pageSize": "20", "searchType": "3", "timeType": "0"}, req_type='bbs')
            if res_posts.get('code') == 200:
                posts = res_posts.get('data', {}).get('postList', [])

        # 3. 浏览帖子
        if tasks_map.get("浏览3篇帖子", 1) == 0 and posts:
            view_count = 0
            for p in posts[:3]:
                self._req(API.FORUM_POST_DETAIL, data={"isOnlyPublisher": "0", "postId": p['postId'], "showOrderTyper": "2"}, req_type='bbs')
                view_count += 1
                time.sleep(random.uniform(1, 2))
            self._log(f"完成浏览帖子任务 ({view_count}/3)")

        # 4. 点赞帖子
        if tasks_map.get("点赞5次", 1) == 0 and posts:
            like_count = 0
            for p in posts[:5]:
                self._req(API.FORUM_LIKE, data={"forumId": 11, "gameId": 3, "likeType": 1, "operateType": 1, "postCommentId": "", "postCommentReplyId": "", "postId": p['postId'], "postType": 1, "toUserId": p['userId']}, req_type='bbs')
                like_count += 1
                time.sleep(random.uniform(1, 2))
            self._log(f"完成点赞帖子任务 ({like_count}/5)")

        # 5. 分享帖子
        if tasks_map.get("分享1次帖子", 1) == 0:
            self._req(API.TASK_SHARE, data={"gameId": 3}, req_type='bbs')
            self._log("完成分享帖子任务 (1/1)")

    def run(self):
        try:
            if self.init_user_data():
                self.game_sign()
                self.forum_tasks()
        except Exception as e:
            self._log(f"执行异常: {str(e)}")
            self.success = False
        return "\n".join(self.messages)

# ================= 主程序入口 =================
def get_tokens() -> List[Dict[str, str]]:
    """读取环境变量 KURO_TOKEN，格式：Token # 备注名，多个账号换行或使用 & 分隔"""
    raw = os.environ.get("KURO_TOKEN", "").strip()
    if not raw:
        return []

    raw = raw.replace('&', '\n').replace(',', '\n')
    token_list = []
    
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        parts = line.split('#', 1)
        token_val = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else f"账号{len(token_list) + 1}"
        
        if token_val:
            token_list.append({'token': token_val, 'note': note})
            
    return token_list

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    
    tokens = get_tokens()
    if not tokens:
        logging.error("未找到 Token，请在环境变量中设置 'KURO_TOKEN'。")
        return

    logging.info(f"✅ 检测到 {len(tokens)} 个账号，开始执行库街区签到...\n" + "-" * 30)
    
    notify_content = []
    
    for token_data in tokens:
        signer = KuroSigner(token_data)
        result_msg = signer.run()
        
        status_icon = "✅" if signer.success else "❌"
        header = f"【{signer.note}】{status_icon}"
        
        notify_content.append(header)
        notify_content.append(result_msg)
        notify_content.append("-" * 20)
        
    final_content = "\n".join(notify_content)
    logging.info(f"\n{final_content}")
    
    if send:
        send("库街区签到", final_content)

if __name__ == '__main__':
    main()