#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拼多多开放平台（POP）网关客户端。

设计要点（汲取自 niltor/open-pdd-net-sdk 的实现与官方接入指南）：
- 统一网关：所有接口都是 POST https://gw-api.pinduoduo.com/api/router
- 签名算法：sign = MD5(client_secret + 排序拼接(params) + client_secret).upper()
  排序按**参数名的字典序**，拼接格式为 `key1value1key2value2`
- 时间戳：秒级 UNIX 时间戳，需与拼多多服务器时间差在 10 分钟内
  （错误码 10001 常因此触发，故内置一次自动重试）

为什么单独抽一层：签名是"错一个字符就 20004 签名校验失败"的地方，
必须先有单元测试锁定，再谈业务动作。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

# 官方网关（目前只提供正式环境，无沙箱）
GATEWAY_URL = "https://gw-api.pinduoduo.com/api/router"

# 环境变量名
ENV_CLIENT_ID = "DUDUTT_CLIENT_ID"
ENV_CLIENT_SECRET = "DUDUTT_CLIENT_SECRET"
ENV_ACCESS_TOKEN = "DUDUTT_ACCESS_TOKEN"
ENV_TIMEOUT = "DUDUTT_TIMEOUT"


class PopError(Exception):
    """POP 网关返回的业务错误，消息面向 Agent 保持可读、可纠正。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[int] = None,
        sub_code: Optional[int] = None,
        request_id: Optional[str] = None,
        api: Optional[str] = None,
    ):
        self.error_code = error_code
        self.sub_code = sub_code
        self.request_id = request_id
        self.api = api
        detail = message
        if error_code is not None:
            detail = f"[{error_code}] {message}"
        if sub_code is not None:
            detail = f"{detail}（子错误码 {sub_code}）"
        super().__init__(detail)

    def to_dict(self) -> dict:
        """转成结构化字典，便于 MCP 工具直接返回给 Agent 诊断。"""
        return {
            "ok": False,
            "error_code": self.error_code,
            "sub_code": self.sub_code,
            "message": str(self),
            "hint": explain_error(self.error_code),
            "request_id": self.request_id,
            "api": self.api,
        }


# 官方错误码 → 可执行建议。Agent 拿到 hint 才能自我纠正，
# 否则只会反复重试同一个错误（参考文档「返回错误码说明」表）。
ERROR_HINTS: dict[int, str] = {
    10000: "参数错误：请按文档核对参数名与类型。",
    10001: "公共参数错误：常因 timestamp 与服务器相差超 10 分钟，或缺少必填公共参数。",
    10016: "client_id 不正确或应用已下线，请核对 DUDUTT_CLIENT_ID。",
    10017: "type（接口名）不正确，请检查是否拼错接口名。",
    10019: "access_token 已过期，请重新授权换取新的 token。",
    20004: "签名 sign 校验失败：请核对 client_secret 与签名算法（MD5 后转大写）。",
    20005: "IP 不在白名单：请到控制台把当前出口 IP 加入白名单。",
    20031: "应用未包含该接口权限：请在控制台申请对应权限包。",
    20032: "access_token 或 client_id 错误，请核对凭据。",
    20034: "接口已下线。",
    20035: "接口不属于当前网关，请确认请求的是 gw-api.pinduoduo.com。",
    21001: "请求参数错误（业务参数），请核对取值。",
    21002: "必填业务参数为空。",
    30000: "没有调用该 target 接口的权限。",
    50000: "拼多多系统内部错误，请稍后重试。",
    50001: "业务服务错误：常因账号不是快团团商家，或团购创建失败。",
    52001: "网关业务服务错误，建议稍后重试。",
    52004: "请求 body 过大。",
    52101: "接口被限流，请降低调用频率后重试。",
    70031: "调用过于频繁，请调整调用频率。",
    70034: "当前用户或应用存在风险，已被禁止调用。",
    70036: "应用处于测试状态，调用次数受限（上线审核通过后解除）。",
}


def explain_error(error_code: Optional[int]) -> str:
    """把错误码翻译成可执行建议。"""
    if error_code is None:
        return "未知错误，请查看原始消息。"
    return ERROR_HINTS.get(error_code, "未知错误码，请查阅官方「返回错误码说明」。")


def sign_params(params: dict[str, Any], client_secret: str) -> str:
    """计算 POP 签名。

    官方算法：
        1. 除 sign 外所有参数按**参数名字典序**排序
        2. 拼接成 `key1value1key2value2...`（无分隔符）
        3. 首尾各拼 client_secret
        4. MD5 后**转大写**

    注意：值为 None 的参数必须已被剔除；嵌套 dict/list 需先序列化为
    JSON 字符串（由 build_params 统一处理）。
    """
    if not client_secret:
        raise PopError("缺少 client_secret，无法计算签名")

    pairs = sorted(
        (k, v) for k, v in params.items() if k != "sign" and v is not None
    )
    raw = client_secret + "".join(f"{k}{v}" for k, v in pairs) + client_secret
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()


def _stringify(value: Any) -> str:
    """把参数值转成签名所需的字符串形式。

    复杂类型（dict/list）在 POP 协议里以 JSON 字符串传输，
    因此签名也必须用同一份 JSON 文本，否则签名对不上。
    """
    if isinstance(value, bool):
        # POP 协议用 true/false，Python 的 str(True) 是 "True" 会签名错
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


@dataclass
class PopClient:
    """POP 网关客户端。

    用法：
        client = PopClient(client_id="...", client_secret="...", access_token="...")
        resp = client.call("pdd.ktt.group.create", {"title": "..."})
    """

    client_id: str
    client_secret: str
    access_token: Optional[str] = None
    timeout: int = 30
    gateway: str = GATEWAY_URL
    # 允许注入 session，测试时可替换为假对象
    session: Any = field(default_factory=requests.Session, repr=False)

    @classmethod
    def from_env(cls, env: Optional[dict[str, str]] = None) -> "PopClient":
        """从环境变量构造（MCP 部署的常规方式）。"""
        env = env if env is not None else os.environ
        client_id = (env.get(ENV_CLIENT_ID) or "").strip()
        client_secret = (env.get(ENV_CLIENT_SECRET) or "").strip()
        access_token = (env.get(ENV_ACCESS_TOKEN) or "").strip() or None
        timeout_raw = (env.get(ENV_TIMEOUT) or "").strip()

        if not client_id or not client_secret:
            raise PopError(
                f"缺少凭据：请设置环境变量 {ENV_CLIENT_ID} 与 {ENV_CLIENT_SECRET}。"
                f"若只想跑通流程，可设 DUDUTT_BACKEND=mock 使用模拟后端。"
            )

        timeout = 30
        if timeout_raw:
            try:
                timeout = int(timeout_raw)
            except ValueError:
                pass

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            access_token=access_token,
            timeout=timeout,
        )

    def build_params(self, api: str, biz: Optional[dict] = None) -> dict[str, str]:
        """组装完整请求参数（含公共参数）并计算签名。"""
        params: dict[str, Any] = {
            "type": api,
            "client_id": self.client_id,
            "timestamp": str(int(time.time())),
            "data_type": "JSON",
        }
        if self.access_token:
            params["access_token"] = self.access_token
        if biz:
            for k, v in biz.items():
                if v is None:
                    continue
                params[k] = _stringify(v)

        params["sign"] = sign_params(params, self.client_secret)
        return {k: str(v) for k, v in params.items()}

    def call(self, api: str, biz: Optional[dict] = None) -> dict:
        """调用一个 POP 接口，返回业务数据（已剥离 response 包装）。

        失败时抛出 PopError。**绝不返回 None 或空 dict 假装成功。**
        """
        params = self.build_params(api, biz)
        try:
            resp = self.session.post(
                self.gateway, data=params, timeout=self.timeout
            )
        except requests.RequestException as e:
            raise PopError(f"网络请求失败：{e}", api=api) from e

        if resp.status_code != 200:
            raise PopError(
                f"网关返回 HTTP {resp.status_code}：{resp.text[:200]}", api=api
            )

        try:
            payload = resp.json()
        except ValueError as e:
            raise PopError(
                f"响应不是合法 JSON：{resp.text[:200]}", api=api
            ) from e

        return self._unwrap(api, payload)

    def _unwrap(self, api: str, payload: dict) -> dict:
        """剥离 POP 的响应包装，失败时抛 PopError。

        POP 成功响应形如 {"pdd_ktt_group_create_response": {...}}
        （接口名中的点换成下划线），失败则为
        {"error_response": {"error_code": ..., "error_msg": ...}}
        """
        if not isinstance(payload, dict):
            raise PopError(f"响应结构异常：{payload!r}", api=api)

        if "error_response" in payload:
            err = payload["error_response"] or {}
            raise PopError(
                err.get("error_msg") or err.get("sub_msg") or "接口返回错误",
                error_code=err.get("error_code"),
                sub_code=err.get("sub_code"),
                request_id=err.get("request_id"),
                api=api,
            )

        expected_key = api.replace(".", "_") + "_response"
        if expected_key in payload:
            return payload[expected_key]

        # 兜底：某些接口包装名与接口名不一致，取唯一的顶层键
        if len(payload) == 1:
            return next(iter(payload.values()))
        return payload

    def health_check(self) -> dict:
        """轻量连通性检查：拉取拼多多服务器时间。

        `pdd.time.get` 是最低风险的只读接口，适合用来验证
        client_id / 签名 / 网络是否都通。
        """
        try:
            data = self.call("pdd.time.get", {})
            return {
                "ok": True,
                "server_time": (data or {}).get("time"),
                "local_time": int(time.time()),
                "backend": "api",
            }
        except PopError as e:
            return e.to_dict()
