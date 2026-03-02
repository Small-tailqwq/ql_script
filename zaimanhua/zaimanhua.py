# -*- coding: utf-8 -*-
"""
cron: 20 7 * * *
new Env('再漫画自动签到');
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

try:
	from sendNotify import send  # type: ignore
except Exception:  # noqa: BLE001
	try:
		from notify import send  # type: ignore
	except Exception:
		send = None


API_BASE = "https://i.zaimanhua.com/lpi/v1"
DEFAULT_TIMEOUT = 15
DEBUG_ENABLED = os.getenv("ZAIMANHUA_DEBUG", "0").strip().lower() in {"1", "true", "on", "yes"}


def debug_dump(label: str, payload: Any) -> None:
	if not DEBUG_ENABLED:
		return
	try:
		fragment = json.dumps(payload, ensure_ascii=False)[:1500]
	except Exception:  # noqa: BLE001
		fragment = str(payload)[:1500]
	logging.debug("%s: %s", label, fragment)


@dataclass
class SignResult:
	account: str
	success: bool
	message: str


class ZaiManHua:
	name = "再漫画"

	def __init__(self, username: str, password: str, alias: Optional[str] = None) -> None:
		self.username = username.strip()
		self.password = password.strip()
		self.alias = alias.strip() if alias else ""
		self.session = self._build_session()

	@staticmethod
	def _build_session() -> requests.Session:
		session = requests.Session()
		session.headers.update(
			{
				"User-Agent": (
					"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
					"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
				),
				"Accept": "application/json, text/plain, */*",
				"Accept-Language": "zh-CN,zh;q=0.9",
				"Origin": "https://m.zaimanhua.com",
				"Referer": "https://m.zaimanhua.com/",
			}
		)
		return session

	@staticmethod
	def _md5(text: str) -> str:
		return hashlib.md5(text.encode("utf-8")).hexdigest()

	def _request_json(
		self,
		method: str,
		endpoint: str,
		*,
		params: Optional[Dict[str, Any]] = None,
		json_data: Optional[Dict[str, Any]] = None,
		headers: Optional[Dict[str, str]] = None,
	) -> Dict[str, Any]:
		url = endpoint if endpoint.startswith("http") else f"{API_BASE}/{endpoint.lstrip('/') }"
		if DEBUG_ENABLED:
			logging.debug(
				"请求 %s %s params=%s json=%s headers=%s",
				method,
				url,
				params,
				json_data,
				headers,
			)
		response = self.session.request(
			method,
			url,
			params=params,
			json=json_data,
			headers=headers,
			timeout=DEFAULT_TIMEOUT,
		)
		response.raise_for_status()
		data = response.json()
		if not isinstance(data, dict):  # pragma: no cover - 防御
			raise ValueError("接口返回数据格式异常")
		debug_dump(f"响应 {method} {url}", data)
		return data

	@staticmethod
	def _ensure_success(payload: Dict[str, Any], allowed_errno: Iterable[int] = (0,)) -> Tuple[int, str]:
		errno = int(payload.get("errno", -1))
		errmsg = str(payload.get("errmsg", ""))
		if errno not in allowed_errno:
			raise RuntimeError(f"接口返回错误 errno={errno}, errmsg={errmsg}")
		return errno, errmsg

	@staticmethod
	def _extract_token(payload: Dict[str, Any]) -> Optional[str]:
		def _search(node: Any) -> Optional[str]:
			if isinstance(node, dict):
				for key, value in node.items():
					key_lower = str(key).lower()
					if key_lower in {"token", "access_token"} and isinstance(value, str) and value:
						return value
					if isinstance(value, (dict, list)):
						found = _search(value)
						if found:
							return found
			elif isinstance(node, list):
				for item in node:
					found = _search(item)
					if found:
						return found
			return None

		return _search(payload)

	@staticmethod
	def _find_first(node: Any, target_keys: Iterable[str]) -> Optional[Any]:
		target = {str(key).lower() for key in target_keys}
		def _search(current: Any) -> Optional[Any]:
			if isinstance(current, dict):
				for key, value in current.items():
					if str(key).lower() in target and value is not None:
						return value
					if isinstance(value, (dict, list)):
						found = _search(value)
						if found is not None:
							return found
			elif isinstance(current, list):
				for item in current:
					found = _search(item)
					if found is not None:
						return found
			return None

		return _search(node)

	def _login(self) -> str:
		payload = self._request_json(
			"POST",
			"login/passwd",
			params={"username": self.username, "passwd": self._md5(self.password)},
		)
		self._ensure_success(payload)
		token: Optional[str] = None
		token_source = "未知"
		data = payload.get("data")
		if isinstance(data, dict):
			token = self._extract_token(data)
			if token:
				token_source = "data"
		if not token:
			token = self._extract_token(payload)
			if token:
				token_source = "payload"
		if not token and self.session.cookies:
			token = self.session.cookies.get("token") or self.session.cookies.get("Authorization")
			if token:
				token_source = "cookies"
		if not token:
			snippet = str(payload)[:300]
			raise RuntimeError(f"登录成功但未返回 token，响应片段：{snippet}")
		logging.debug("登录成功，token 来源=%s", token_source)
		return str(token)

	def _sign_in(self, token: str) -> str:
		payload = self._request_json(
			"POST",
			"task/sign_in",
			headers={"Authorization": f"Bearer {token}"},
		)
		_, errmsg = self._ensure_success(payload, allowed_errno=(0, 1))
		return errmsg or "签到成功"

	def _fetch_user_info(self, token: str) -> Tuple[str, Optional[int]]:
		payload = self._request_json(
			"POST",
			"u_center/passport/message",
			headers={"Authorization": f"Bearer {token}"},
		)
		self._ensure_success(payload)
		data = payload.get("data")
		debug_dump("用户信息 payload", payload)
		if not isinstance(data, dict):
			raise RuntimeError("用户信息数据格式异常")
		user_info = data.get("userInfo") or data.get("user") or data
		if not isinstance(user_info, dict):
			user_info = {}
		nickname = str(
			user_info.get("nickname")
			or user_info.get("username")
			or data.get("nickname")
			or ""
		)
		level_value = user_info.get("user_level") or data.get("user_level")
		if level_value is None:
			level_value = self._find_first(data, {"user_level", "level"})
		try:
			level = int(level_value) if level_value is not None else None
		except (TypeError, ValueError):
			level = None
		return nickname, level

	def _fetch_task_info(self, token: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
		payload = self._request_json(
			"GET",
			"task/list",
			headers={"Authorization": f"Bearer {token}"},
		)
		self._ensure_success(payload)
		data = payload.get("data")
		debug_dump("任务列表 payload", payload)
		if not isinstance(data, dict):
			raise RuntimeError("任务列表数据格式异常")
		user_currency = data.get("userCurrency")
		if not isinstance(user_currency, dict):
			task_section = data.get("task")
			if isinstance(task_section, dict):
				user_currency = task_section.get("userCurrency")
		credits = self._safe_int(user_currency, "credits") if isinstance(user_currency, dict) else None
		if credits is None:
			found = self._find_first(data, {"credits"})
			try:
				credits = int(found) if found is not None else None
			except (TypeError, ValueError):
				credits = None

		sum_sign_task = (
			data.get("sumSignTask")
			or data.get("signTask")
			or (data.get("task") or {}).get("sumSignTask")
			or (data.get("task") or {}).get("signTask")
			or {}
		)
		continuous_days = self._safe_int(sum_sign_task, "continuousSignDays")
		history_days = self._safe_int(sum_sign_task, "sumSignDays")
		if continuous_days is None:
			value = self._find_first(data, {"continuousSignDays", "continuous_days"})
			try:
				continuous_days = int(value) if value is not None else None
			except (TypeError, ValueError):
				continuous_days = None
		if history_days is None:
			value = self._find_first(data, {"sumSignDays", "totalSignDays", "history_days"})
			try:
				history_days = int(value) if value is not None else None
			except (TypeError, ValueError):
				history_days = None
		return credits, continuous_days, history_days

	@staticmethod
	def _safe_int(source: Any, key: str) -> Optional[int]:
		value: Any = None
		if isinstance(source, dict):
			value = source.get(key)
		try:
			return int(value) if value is not None else None
		except (TypeError, ValueError):
			return None

	@staticmethod
	def _mask(text: str) -> str:
		text = text or ""
		if len(text) <= 2:
			return f"{text[:1]}*" if text else "未知"
		return f"{text[0]}***{text[-1]}"

	def main(self) -> SignResult:
		if not self.username or not self.password:
			raise RuntimeError("账号或密码未配置")

		token = self._login()
		sign_msg = self._sign_in(token)
		nickname, level = self._fetch_user_info(token)
		credits, continuous_days, history_days = self._fetch_task_info(token)

		display_name = nickname or self.alias or self._mask(self.username)
		level_info = f"LV{level}" if level is not None else "未知"
		credit_info = str(credits) if credits is not None else "未知"
		continuous_info = f"{continuous_days}天" if continuous_days is not None else "未知"
		history_info = f"{history_days}天" if history_days is not None else "未知"

		lines = [
			f"签到状态：{sign_msg}",
			f"用户等级：{level_info}",
			f"当前积分：{credit_info}",
			f"连续签到：{continuous_info}",
			f"历史签到：{history_info}",
		]

		return SignResult(
			account=display_name,
			success=True,
			message="\n".join(lines),
		)


def load_accounts() -> List[ZaiManHua]:
	accounts: List[ZaiManHua] = []

	raw_accounts = os.getenv("ZAIMANHUA_ACCOUNTS", "").strip()
	if raw_accounts:
		for line in raw_accounts.splitlines():
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			parts = line.split("#", 2)
			if len(parts) < 2:
				logging.warning("无效的账号配置行：%s，格式应为 用户名#密码[#别名]", line)
				continue
			username, password, *rest = parts
			alias = rest[0] if rest else None
			accounts.append(ZaiManHua(username=username, password=password, alias=alias))

	username = os.getenv("ZAIMANHUA_USERNAME", "").strip()
	password = os.getenv("ZAIMANHUA_PASSWORD", "").strip()
	alias = os.getenv("ZAIMANHUA_ALIAS", "").strip()

	if not accounts and username and password:
		accounts.append(ZaiManHua(username=username, password=password, alias=alias))

	return accounts


def format_report(results: List[SignResult]) -> str:
	chunks = []
	for item in results:
		status = "✅ 成功" if item.success else "❌ 失败"
		chunks.append(f"账号：{item.account} | {status}\n{item.message}")
	return "\n\n".join(chunks)


def main() -> None:
	logging.basicConfig(
		level=logging.DEBUG if DEBUG_ENABLED else logging.INFO,
		format="%(asctime)s [%(levelname)s] %(message)s",
	)
	if DEBUG_ENABLED:
		logging.debug("调试模式已开启 (ZAIMANHUA_DEBUG=1)")

	accounts = load_accounts()
	if DEBUG_ENABLED and accounts:
		masked_accounts = [
			{
				"username": ZaiManHua._mask(acc.username),
				"alias": acc.alias,
			}
			for acc in accounts
		]
		debug_dump("已加载账号", masked_accounts)
	if not accounts:
		logging.error("未配置再漫画账号信息，需设置 ZAIMANHUA_ACCOUNTS 或 ZAIMANHUA_USERNAME/ZAIMANHUA_PASSWORD。")
		if send:
			send("再漫画签到", "未配置账号信息，任务未执行。")
		return

	results: List[SignResult] = []
	for index, account in enumerate(accounts, start=1):
		try:
			logging.info("[%s] 正在执行账号 %s", index, account.alias or account.username)
			results.append(account.main())
		except Exception as exc:  # noqa: BLE001
			logging.exception("[%s] 账号 %s 执行失败：%s", index, account.alias or account.username, exc)
			results.append(
				SignResult(
					account=account.alias or account.username,
					success=False,
					message=str(exc),
				)
			)

	report = format_report(results)
	logging.info("\n%s", report)
	if send:
		send("再漫画签到", report)


if __name__ == "__main__":
	main()
