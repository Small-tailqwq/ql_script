# -*- coding: utf-8 -*-
"""
cron: 0 8 * * *
new Env('森空岛自动签到');
"""

import base64
import gzip
import hashlib
import hmac
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib import parse

import requests

# 尝试导入 cryptography，这是森空岛加密算法必须的库
try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:
    print("错误: 缺少依赖 'cryptography'。请在青龙面板-依赖管理-Python3中安装 'cryptography'。")
    exit(1)

# 尝试导入青龙通知
try:
    from sendNotify import send  # type: ignore
except Exception:
    try:
        from notify import send  # type: ignore
    except Exception:
        send = None

# ================= 配置常量 =================
DEFAULT_TIMEOUT = 30
APP_CODE = '4ca99fa6b56cc2ba'
DEVICES_INFO_URL = "https://fp-it.portal101.cn/deviceprofile/v4"
LOGIN_CODE_URL = "https://as.hypergryph.com/general/v1/send_phone_code"
TOKEN_PHONE_CODE_URL = "https://as.hypergryph.com/user/auth/v2/token_by_phone_code"
TOKEN_PASSWORD_URL = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
GRANT_CODE_URL = "https://as.hypergryph.com/user/oauth2/v2/grant"
CRED_CODE_URL = "https://zonai.skland.com/web/v1/user/auth/generate_cred_by_code"
BINDING_URL = "https://zonai.skland.com/api/v1/game/player/binding"
SIGN_URL_MAPPING = {
    'arknights': 'https://zonai.skland.com/api/v1/game/attendance',
    'endfield': 'https://zonai.skland.com/web/v1/game/endfield/attendance'
}

# ================= 数美(SecuritySm) 加密逻辑整合 =================
# 原作者: xxyz30 / Modified for QingLong
class SecurityUtils:
    SM_CONFIG = {
        "organization": "UWXspnCCJN4sfYlNfqps",
        "appId": "default",
        "publicKey": "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCmxMNr7n8ZeT0tE1R9j/mPixoinPkeM+k4VGIn/s0k7N5rJAfnZ0eMER+QhwFvshzo0LNmeUkpR8uIlU/GEVr8mN28sKmwd2gpygqj0ePnBmOW4v0ZVwbSYK+izkhVFk2V/doLoMbWy6b+UnA8mkjvg0iYWRByfRsK2gdl7llqCwIDAQAB",
        "protocol": "https",
        "apiHost": "fp-it.portal101.cn"
    }
    
    DES_RULE = {
        "appId": {"cipher": "DES", "is_encrypt": 1, "key": "uy7mzc4h", "obfuscated_name": "xx"},
        "box": {"is_encrypt": 0, "obfuscated_name": "jf"},
        "canvas": {"cipher": "DES", "is_encrypt": 1, "key": "snrn887t", "obfuscated_name": "yk"},
        "clientSize": {"cipher": "DES", "is_encrypt": 1, "key": "cpmjjgsu", "obfuscated_name": "zx"},
        "organization": {"cipher": "DES", "is_encrypt": 1, "key": "78moqjfc", "obfuscated_name": "dp"},
        "os": {"cipher": "DES", "is_encrypt": 1, "key": "je6vk6t4", "obfuscated_name": "pj"},
        "platform": {"cipher": "DES", "is_encrypt": 1, "key": "pakxhcd2", "obfuscated_name": "gm"},
        "plugins": {"cipher": "DES", "is_encrypt": 1, "key": "v51m3pzl", "obfuscated_name": "kq"},
        "pmf": {"cipher": "DES", "is_encrypt": 1, "key": "2mdeslu3", "obfuscated_name": "vw"},
        "protocol": {"is_encrypt": 0, "obfuscated_name": "protocol"},
        "referer": {"cipher": "DES", "is_encrypt": 1, "key": "y7bmrjlc", "obfuscated_name": "ab"},
        "res": {"cipher": "DES", "is_encrypt": 1, "key": "whxqm2a7", "obfuscated_name": "hf"},
        "rtype": {"cipher": "DES", "is_encrypt": 1, "key": "x8o2h2bl", "obfuscated_name": "lo"},
        "sdkver": {"cipher": "DES", "is_encrypt": 1, "key": "9q3dcxp2", "obfuscated_name": "sc"},
        "status": {"cipher": "DES", "is_encrypt": 1, "key": "2jbrxxw4", "obfuscated_name": "an"},
        "subVersion": {"cipher": "DES", "is_encrypt": 1, "key": "eo3i2puh", "obfuscated_name": "ns"},
        "svm": {"cipher": "DES", "is_encrypt": 1, "key": "fzj3kaeh", "obfuscated_name": "qr"},
        "time": {"cipher": "DES", "is_encrypt": 1, "key": "q2t3odsk", "obfuscated_name": "nb"},
        "timezone": {"cipher": "DES", "is_encrypt": 1, "key": "1uv05lj5", "obfuscated_name": "as"},
        "tn": {"cipher": "DES", "is_encrypt": 1, "key": "x9nzj1bp", "obfuscated_name": "py"},
        "trees": {"cipher": "DES", "is_encrypt": 1, "key": "acfs0xo4", "obfuscated_name": "pi"},
        "ua": {"cipher": "DES", "is_encrypt": 1, "key": "k92crp1t", "obfuscated_name": "bj"},
        "url": {"cipher": "DES", "is_encrypt": 1, "key": "y95hjkoo", "obfuscated_name": "cf"},
        "version": {"is_encrypt": 0, "obfuscated_name": "version"},
        "vpw": {"cipher": "DES", "is_encrypt": 1, "key": "r9924ab5", "obfuscated_name": "ca"}
    }

    BROWSER_ENV = {
        'plugins': 'MicrosoftEdgePDFPluginPortableDocumentFormatinternal-pdf-viewer1,MicrosoftEdgePDFViewermhjfbmdgcfjbbpaeojofohoefgiehjai1',
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0',
        'canvas': '259ffe69',
        'timezone': -480,
        'platform': 'Win32',
        'url': 'https://www.skland.com/',
        'referer': '',
        'res': '1920_1080_24_1.25',
        'clientSize': '0_0_1080_1920_1920_1080_1920_1080',
        'status': '0011',
    }

    @staticmethod
    def _des_encrypt(o: dict) -> dict:
        result = {}
        for i in o.keys():
            if i in SecurityUtils.DES_RULE.keys():
                rule = SecurityUtils.DES_RULE[i]
                res = o[i]
                if rule.get('is_encrypt') == 1:
                    c = Cipher(TripleDES(rule['key'].encode('utf-8')), modes.ECB())
                    data = str(res).encode('utf-8')
                    # PKCS5/PKCS7 padding equivalent logic manually implemented or handled
                    # Manual zero padding as per original code (though original said \x00*8, TripleDES block is 8)
                    pad_len = 8 - (len(data) % 8)
                    data += b'\x00' * pad_len
                    encryptor = c.encryptor()
                    encrypted_bytes = encryptor.update(data) + encryptor.finalize()
                    res = base64.b64encode(encrypted_bytes).decode('utf-8')
                result[rule['obfuscated_name']] = res
            else:
                result[i] = o[i]
        return result

    @staticmethod
    def _aes_encrypt(v: bytes, k: bytes) -> str:
        iv = '0102030405060708'
        c = Cipher(algorithms.AES(k), modes.CBC(iv.encode('utf-8')))
        # Manual Zero padding logic from original code
        v_padded = v + b'\x00'
        while len(v_padded) % 16 != 0:
            v_padded += b'\x00'
        encryptor = c.encryptor()
        return (encryptor.update(v_padded) + encryptor.finalize()).hex()

    @staticmethod
    def _gzip_compress(o: dict) -> bytes:
        json_str = json.dumps(o, ensure_ascii=False)
        return gzip.compress(json_str.encode('utf-8'), 2, mtime=0)

    @staticmethod
    def _get_tn(o: dict) -> str:
        sorted_keys = sorted(o.keys())
        result_list = []
        for i in sorted_keys:
            v = o[i]
            if isinstance(v, (int, float)):
                v = str(v * 10000)
            elif isinstance(v, dict):
                v = SecurityUtils._get_tn(v)
            result_list.append(str(v))
        return ''.join(result_list)

    @staticmethod
    def _get_smid() -> str:
        t = time.localtime()
        _time = '{}{:0>2d}{:0>2d}{:0>2d}{:0>2d}{:0>2d}'.format(
            t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
        uid = str(uuid.uuid4())
        v = _time + hashlib.md5(uid.encode('utf-8')).hexdigest() + '00'
        smsk_web = hashlib.md5(('smsk_web_' + v).encode('utf-8')).hexdigest()[0:14]
        return v + smsk_web + '0'

    @classmethod
    def get_d_id(cls) -> str:
        try:
            pk = serialization.load_der_public_key(base64.b64decode(cls.SM_CONFIG['publicKey']))
            uid = str(uuid.uuid4()).encode('utf-8')
            pri_id = hashlib.md5(uid).hexdigest()[0:16]
            
            ep = pk.encrypt(uid, padding.PKCS1v15())
            ep_str = base64.b64encode(ep).decode('utf-8')

            browser = cls.BROWSER_ENV.copy()
            current_time = int(time.time() * 1000)
            browser.update({
                'vpw': str(uuid.uuid4()),
                'svm': current_time,
                'trees': str(uuid.uuid4()),
                'pmf': current_time
            })

            des_target = {
                **browser,
                'protocol': 102,
                'organization': cls.SM_CONFIG['organization'],
                'appId': cls.SM_CONFIG['appId'],
                'os': 'web',
                'version': '3.0.0',
                'sdkver': '3.0.0',
                'box': '',
                'rtype': 'all',
                'smid': cls._get_smid(),
                'subVersion': '1.0.0',
                'time': 0
            }
            des_target['tn'] = hashlib.md5(cls._get_tn(des_target).encode()).hexdigest()
            
            # GZIP -> Base64(implicitly handled in _AES logic in original code? No, original returns bytes)
            # Original code: _AES(GZIP(_DES(des_target)), priId...)
            # Note: The original _DES returns a dict. _GZIP takes a dict and returns b64 encoded bytes inside gzip stream.
            
            des_output = cls._des_encrypt(des_target)
            gzip_output = base64.b64encode(cls._gzip_compress(des_output)) # Original GZIP function returns b64 encoded
            
            # Original code passes the result of GZIP (which is b64 bytes) to AES
            des_result = cls._aes_encrypt(gzip_output, pri_id.encode('utf-8'))

            response = requests.post(DEVICES_INFO_URL, json={
                'appId': 'default',
                'compress': 2,
                'data': des_result,
                'encode': 5,
                'ep': ep_str,
                'organization': cls.SM_CONFIG['organization'],
                'os': 'web'
            }, timeout=10)

            resp = response.json()
            if resp['code'] != 1100:
                logging.error(f"数美设备注册失败: {resp}")
                return 'B' + str(uuid.uuid4()) # Fallback
            
            return 'B' + resp['detail']['deviceId']
        except Exception as e:
            logging.error(f"计算dId时发生错误: {e}")
            # Fallback random UUID if calculation fails
            return 'B' + str(uuid.uuid4())

# ================= 业务逻辑 =================

@dataclass
class SignResult:
    account_mask: str
    success: bool
    messages: List[str]

class SkylandSigner:
    def __init__(self, token_data: Dict[str, str]):
            # 接收字典：{'token': '...', 'note': '...'}
            self.raw_token = token_data['token']
            self.note = token_data.get('note')
            self.user_token = self._parse_token(self.raw_token)
            # ... (其他初始化代码保持不变: self.cred, self.d_id, self.session 等)
            self.cred: str = ""
            self.session_token: str = "" 
            self.d_id = SecurityUtils.get_d_id()
            self.session = requests.Session()
            self.headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12; SM-A5560 Build/V417IR; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36; SKLand/1.52.1',
                'Accept-Encoding': 'gzip',
                'Connection': 'close',
                'dId': self.d_id,
                'X-Requested-With': 'com.hypergryph.skland'
            }
            self.sign_headers_base = {
                'platform': '3',
                'timestamp': '',
                'dId': self.d_id,
                'vName': '1.0.0'
            }

    @staticmethod
    def _parse_token(raw_token: str) -> str:
        """兼容 JSON 格式或纯字符串格式的 Token"""
        try:
            t = json.loads(raw_token)
            return t['data']['content']
        except:
            return raw_token.strip()

    def _generate_signature(self, path: str, body_or_query: str):
        """生成 HMAC-SHA256 + MD5 签名"""
        # 时间戳 -2 秒以避免服务器判定时间过快
        t = str(int(time.time()) - 2)
        # 注意：这里使用的是 cred 接口换取到的临时 session_token 进行签名
        token_bytes = self.session_token.encode('utf-8')
        
        header_ca = self.sign_headers_base.copy()
        header_ca['timestamp'] = t
        header_ca_str = json.dumps(header_ca, separators=(',', ':'))
        
        s = path + body_or_query + t + header_ca_str
        hex_s = hmac.new(token_bytes, s.encode('utf-8'), hashlib.sha256).hexdigest()
        md5_sign = hashlib.md5(hex_s.encode('utf-8')).hexdigest()
        
        return md5_sign, header_ca

    def _get_sign_headers(self, url: str, method: str, body: Optional[dict]) -> dict:
        h = self.headers.copy()
        h['cred'] = self.cred
        
        p = parse.urlparse(url)
        content = ""
        if method.lower() == 'get':
            content = p.query
        else:
            content = json.dumps(body) if body is not None else ""
            
        sign, header_ca = self._generate_signature(p.path, content)
        h['sign'] = sign
        for k, v in header_ca.items():
            h[k] = v
        return h

    def login(self):
        """使用 Hypergryph Token 换取 Cred 和 Session Token"""
        # 1. Get Grant Code
        resp_grant = self.session.post(GRANT_CODE_URL, json={
            'appCode': APP_CODE,
            'token': self.user_token,
            'type': 0
        }, headers=self.headers).json()
        
        if resp_grant.get('status') != 0:
            raise ValueError(f"获取授权代码失败: {resp_grant.get('msg')}")
        grant_code = resp_grant['data']['code']

        # 2. Get Cred
        resp_cred = self.session.post(CRED_CODE_URL, json={
            'code': grant_code,
            'kind': 1
        }, headers=self.headers).json()
        
        if resp_cred.get('code') != 0:
            raise ValueError(f"获取Cred失败: {resp_cred.get('message')}")
        
        self.cred = resp_cred['data']['cred']
        self.session_token = resp_cred['data']['token'] # 重要：用于签名

    def get_bindings(self) -> List[dict]:
        headers = self._get_sign_headers(BINDING_URL, 'get', None)
        resp = self.session.get(BINDING_URL, headers=headers).json()
        
        if resp['code'] != 0:
            raise ValueError(f"获取绑定角色失败: {resp.get('message')}")
            
        bindings = []
        for app in resp['data']['list']:
            if app.get('appCode') not in SIGN_URL_MAPPING:
                continue
            for char in app.get('bindingList'):
                char['appCode'] = app['appCode']
                bindings.append(char)
        return bindings

    def sign_character(self, character: dict) -> str:
        app_code = character['appCode']
        url = SIGN_URL_MAPPING[app_code]
        
        # 构造请求体
        body = {}
        if app_code == 'arknights':
            body = {'gameId': character.get('gameId'), 'uid': character.get('uid')}
        elif app_code == 'endfield':
            # 终末地通过 sk-game-role 头传递角色信息，Body为空? 参考原代码
            # 原代码 endfield 需要特殊处理 headers
            pass 

        # 签名
        headers = self._get_sign_headers(url, 'post', body if app_code != 'endfield' else None)
        
        # 终末地特殊处理
        if app_code == 'endfield':
            roles = character.get('roles', [])
            msgs = []
            for role in roles:
                headers['Content-Type'] = 'application/json'
                headers['sk-game-role'] = f'3_{role["roleId"]}_{role["serverId"]}'
                headers['referer'] = 'https://game.skland.com/'
                headers['origin'] = 'https://game.skland.com/'
                
                r = self.session.post(url, headers=headers)
                rj = r.json()
                nickname = role.get('nickname', '未知')
                if rj.get('code') != 0:
                     msgs.append(f"[终末地]{nickname}: {rj.get('message')}")
                else:
                    msgs.append(f"[终末地]{nickname}: 签到成功")
            return "\n".join(msgs)
            
        # 明日方舟
        resp = self.session.post(url, headers=headers, json=body).json()
        
        name = character.get('nickName', '未知')
        channel = character.get('channelName', '')
        game_title = "明日方舟" if app_code == 'arknights' else app_code
        
        if resp.get('code') != 0:
            return f"[{game_title}] {name}({channel}): 失败 - {resp.get('message')}"
        
        awards = resp['data']['awards']
        award_str = ",".join([f"{j['resource']['name']}x{j.get('count', 1)}" for j in awards])
        return f"[{game_title}] {name}({channel}): 成功 - 获得 {award_str}"

    def run(self) -> SignResult:
            # 如果有备注，直接用备注；否则用 Token 掩码
            if self.note:
                account_display = self.note
            else:
                account_display = self.user_token[:5] + "***" + self.user_token[-5:]
                
            logs = []
            try:
                self.login()
                bindings = self.get_bindings()
                if not bindings:
                    return SignResult(account_display, False, ["未找到绑定的角色"])
                
                all_success = True
                for char in bindings:
                    try:
                        msg = self.sign_character(char)
                        logs.append(msg)
                        if "失败" in msg:
                            all_success = False
                    except Exception as e:
                        logs.append(f"角色签到异常: {str(e)}")
                        all_success = False
                
                return SignResult(account_display, all_success, logs)
                
            except Exception as e:
                return SignResult(account_display, False, [f"账号执行异常: {str(e)}"])

# ================= 主程序入口 =================

def get_tokens() -> List[Dict[str, str]]:
    """
    从环境变量读取 Token，支持以下格式：
    1. 纯 Token
    2. Token # 备注 (推荐)
    支持通过 换行 或 & 或 , 分割多个账号
    """
    raw = os.environ.get("SK_TOKEN", os.environ.get("TOKEN", "")).strip()
    if not raw:
        return []

    # 预处理：将 & 和 , 统一替换为换行符，以便按行处理
    # 这样可以同时兼容一行写多个（用&分割）和多行写多个
    raw = raw.replace('&', '\n').replace(',', '\n')
    
    token_list = []
    for line in raw.split('\n'):
        line = line.strip()
        if not line:
            continue
            
        # 拆分 Token 和 备注
        parts = line.split('#', 1)
        token_val = parts[0].strip()
        note = parts[1].strip() if len(parts) > 1 else None
        
        if token_val:
            token_list.append({
                'token': token_val,
                'note': note
            })
            
    return token_list

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    tokens = get_tokens() # 这里返回的是 [{'token':..., 'note':...}, ...]
    if not tokens:
        logging.error("未找到 Token。请设置环境变量 'SK_TOKEN'。")
        return

    logging.info(f"检测到 {len(tokens)} 个账号，开始执行...")
    
    notify_content = []
    
    for idx, token_data in enumerate(tokens):
        # 显示备注名，体验更好
        name_display = token_data['note'] if token_data['note'] else f"账号{idx + 1}"
        logging.info(f"--- 正在处理: {name_display} ---")
        
        signer = SkylandSigner(token_data) # 传入整个字典
        result = signer.run()
        
        # 构建日志和通知
        status_icon = "✅" if result.success else "❌"
        header = f"账号: {result.account_mask} {status_icon}"
        logging.info(header)
        for msg in result.messages:
            logging.info(msg)
            
        notify_content.append(header)
        notify_content.extend(result.messages)
        notify_content.append("") 

    # 推送通知
    final_content = "\n".join(notify_content)
    if send:
        send("森空岛自动签到", final_content)

if __name__ == '__main__':
    main()