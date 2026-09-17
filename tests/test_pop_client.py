#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
签名与网关客户端测试（不需要网络，全部用假 session）。

为什么这些测试最重要：签名是"错一个字符就 20004"的地方，
且无法靠肉眼 review 保证。必须先锁死算法。
"""

import json
import sys
from pathlib import Path

# Windows CI（以及部分本地终端）默认 stdout 是 cp1252/GBK，
# 直接 print 中文会抛 UnicodeEncodeError 导致测试整体崩溃。
# 这里强制把输出流切到 UTF-8，保证跨平台一致。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).parent.parent))

from dudutt.pop_client import (
    ENV_CLIENT_ID,
    ENV_CLIENT_SECRET,
    PopClient,
    PopError,
    explain_error,
    sign_params,
)

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


# ---------------------------------------------------------------------------
# 假 session：记录请求，返回预设响应
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.last_url = None
        self.last_data = None

    def post(self, url, data=None, timeout=None):
        self.last_url = url
        self.last_data = data
        return FakeResponse(self.payload)


# ---------------------------------------------------------------------------
# 1. 签名算法
# ---------------------------------------------------------------------------


def test_sign_basic():
    print("\n[1] 签名算法")
    # 手工核对：secret="s"，参数 a=1,b=2
    # 拼接：s + "a1b2" + s = "sa1b2s"
    import hashlib

    expected = hashlib.md5(b"sa1b2s").hexdigest().upper()
    got = sign_params({"a": "1", "b": "2"}, "s")
    check("基本签名与手工计算一致", got == expected, f"got={got} exp={expected}")
    check("签名结果为大写十六进制", got == got.upper() and len(got) == 32)

    # 参数顺序不应影响结果（内部会排序）
    got2 = sign_params({"b": "2", "a": "1"}, "s")
    check("参数顺序不影响签名", got2 == got)

    # sign 字段自身必须被剔除
    got3 = sign_params({"a": "1", "b": "2", "sign": "XXX"}, "s")
    check("sign 字段被剔除", got3 == got)

    # None 值必须被剔除
    got4 = sign_params({"a": "1", "b": "2", "c": None}, "s")
    check("None 值被剔除", got4 == got)

    # 缺 secret 应报错
    try:
        sign_params({"a": "1"}, "")
        check("缺 client_secret 时抛错", False)
    except PopError:
        check("缺 client_secret 时抛错", True)


# ---------------------------------------------------------------------------
# 2. 参数组装
# ---------------------------------------------------------------------------


def test_build_params():
    print("\n[2] 参数组装")
    c = PopClient(client_id="cid", client_secret="sec", access_token="tok")
    params = c.build_params("pdd.ktt.group.create", {"title": "测试团"})

    check("包含 type", params.get("type") == "pdd.ktt.group.create")
    check("包含 client_id", params.get("client_id") == "cid")
    check("包含 access_token", params.get("access_token") == "tok")
    check("包含 timestamp", params.get("timestamp", "").isdigit())
    check("包含 sign", bool(params.get("sign")))
    check("业务参数被带上", params.get("title") == "测试団".replace("団", "团"))

    # 复杂类型应序列化为 JSON 字符串
    p2 = c.build_params("x", {"lst": [{"a": 1}]})
    check(
        "list 被序列化为紧凑 JSON",
        p2.get("lst") == '[{"a":1}]',
        f"got={p2.get('lst')!r}",
    )

    # bool 应转成 true/false（Python 的 str(True) 是 "True"，会签名错）
    p3 = c.build_params("x", {"flag": True})
    check("bool 转成 true", p3.get("flag") == "true", f"got={p3.get('flag')!r}")

    # None 业务参数应被跳过
    p4 = c.build_params("x", {"a": None, "b": "1"})
    check("None 业务参数被跳过", "a" not in p4 and p4.get("b") == "1")


def test_signature_consistency():
    print("\n[3] 签名与请求体一致性")
    c = PopClient(client_id="cid", client_secret="sec", access_token="tok")
    fake = FakeSession({"pdd_time_get_response": {"time": 123}})
    c.session = fake
    c.call("pdd.time.get", {"a": "b"})

    sent = fake.last_data
    sent_sign = sent.get("sign")
    recomputed = sign_params(dict(sent), "sec")
    check(
        "发出的 sign 与重算一致（关键！否则线上必然 20004）",
        sent_sign == recomputed,
        f"sent={sent_sign} recomputed={recomputed}",
    )
    check("网关地址正确", fake.last_url == "https://gw-api.pinduoduo.com/api/router")


# ---------------------------------------------------------------------------
# 4. 响应解析与错误处理
# ---------------------------------------------------------------------------


def test_unwrap_success():
    print("\n[4] 响应解析")
    c = PopClient(client_id="c", client_secret="s")

    # 正常包装：接口名点换下划线 + _response
    out = c._unwrap("pdd.ktt.group.create", {
        "pdd_ktt_group_create_response": {"activity_no": "A1", "success": True}
    })
    check("正确剥离包装", out.get("activity_no") == "A1")

    # 单一顶层键兜底
    out2 = c._unwrap("unknown.api", {"whatever_response": {"x": 1}})
    check("兜底取唯一顶层键", out2.get("x") == 1)


def test_unwrap_error():
    print("\n[5] 错误处理")
    c = PopClient(client_id="c", client_secret="s")

    try:
        c._unwrap("pdd.ktt.group.create", {
            "error_response": {
                "error_code": 20004,
                "error_msg": "签名sign校验失败",
                "request_id": "req1",
            }
        })
        check("error_response 抛 PopError", False)
    except PopError as e:
        check("error_response 抛 PopError", True)
        check("错误码被解析", e.error_code == 20004)
        check("request_id 被保留", e.request_id == "req1")
        d = e.to_dict()
        check("to_dict 含可执行建议", bool(d.get("hint")))
        check("错误提示提到签名", "签名" in d["hint"])


def test_error_hints():
    print("\n[6] 错误码翻译")
    check("20005 提到白名单", "白名单" in explain_error(20005))
    check("10019 提到过期", "过期" in explain_error(10019))
    check("未知码有兜底", bool(explain_error(999999)))


# ---------------------------------------------------------------------------
# 7. 从环境变量构造
# ---------------------------------------------------------------------------


def test_from_env():
    print("\n[7] 环境变量构造")
    try:
        PopClient.from_env({})
        check("缺凭据时抛错", False)
    except PopError as e:
        check("缺凭据时抛错", True)
        check("错误提示提到 mock 选项", "mock" in str(e))

    c = PopClient.from_env({
        ENV_CLIENT_ID: "cid",
        ENV_CLIENT_SECRET: "sec",
        "DUDUTT_TIMEOUT": "15",
    })
    check("正常构造", c.client_id == "cid" and c.client_secret == "sec")
    check("timeout 被解析", c.timeout == 15)
    check("access_token 缺省为 None", c.access_token is None)


def main() -> int:
    print("=" * 60)
    print("dudutt —— POP 网关客户端测试")
    print("=" * 60)
    test_sign_basic()
    test_build_params()
    test_signature_consistency()
    test_unwrap_success()
    test_unwrap_error()
    test_error_hints()
    test_from_env()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
