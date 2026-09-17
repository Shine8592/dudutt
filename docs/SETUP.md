# 接入配置指南（SETUP）

本文档说明如何从零拿到快团团官方 API 凭据并接入 dudutt。

---

## 一、先确认你的路径

| 情况 | 建议 |
|---|---|
| 有企业营业执照 | 走**官方 API**（本文档主线，最稳定合规） |
| 只有个人快团团账号 | 走**浏览器后端**（见第四节），或先用 `mock` 跑通流程 |
| 只想先看看能干什么 | `DUDUTT_BACKEND=mock` 立即体验，无需任何凭据 |

---

## 二、官方 API 接入流程

### ⚠️ 前置门槛

拼多多开放平台官方文档明确：

> **现阶段仅限企业主体资质入驻**

个人开发者无法申请。快团团相关角色为：

- **快团团团长（KTT）** —— 商家自用
- **快团团服务商** —— 为多个团长提供工具

### 步骤

**1. 注册开放平台账号**

访问 <https://open.pinduoduo.com>，手机号验证并同意开发者服务协议。

**2. 角色资质认证**

登录后进入「资质信息」，按业务性质选择角色（快团团团长 / 快团团服务商）。
ERP 服务商或自研系统的商家需走**企业入驻通道**。

**3. 创建应用**

控制台点「创建应用」。命名需遵循格式：

- 软件服务商：`<软件名称>(快团团版)`
- 商家自研：`<商家品牌>自研ERP`

创建后应用处于**测试状态**，可开发测试，但授权商家数与调用量受限。

**4. 申请权限包**

本项目所需接口对应的权限包：

| 接口 | 权限包 |
|---|---|
| `pdd.pop.auth.token.create` | 系统工具 |
| `pdd.ktt.group.create` | **快团团团购管理权限包** |
| `pdd.ktt.goods.*` | 快团团商品相关权限包 |

在控制台为应用勾选对应权限包。若不勾选，调用会返回 `20031 用户没有授权访问此接口`。

**5. 配置 IP 白名单**

若接口限制了 IP，需把本机/服务器出口 IP 加入白名单，
否则返回 `20005 ip无权访问接口，请加入ip白名单`。

**6. OAuth 授权换 token**

构造授权链接（含 `client_id`、`redirect_uri`、`state`），
引导团长扫码授权，拿到 `code` 后调用 `pdd.pop.auth.token.create` 换取
`access_token`（有效期约 1 年，另有 `refresh_token` 可续期）。

**7. 填入环境变量**

```bash
export DUDUTT_CLIENT_ID="你的client_id"
export DUDUTT_CLIENT_SECRET="你的client_secret"
export DUDUTT_ACCESS_TOKEN="换到的access_token"
```

**8. 验证**

```bash
python -c "
from dudutt.pop_client import PopClient
c = PopClient.from_env()
print(c.health_check())
"
```

返回 `{'ok': True, 'server_time': ...}` 说明签名、网络、凭据全部正确。

---

## 三、环境变量清单

| 变量 | 默认 | 说明 |
|---|---|---|
| `DUDUTT_BACKEND` | `api` | `api` / `browser` / `mock` / `auto` |
| `DUDUTT_CLIENT_ID` | — | 开放平台 client_id |
| `DUDUTT_CLIENT_SECRET` | — | 开放平台 client_secret（**务必保密**） |
| `DUDUTT_ACCESS_TOKEN` | — | OAuth 换取的 access_token |
| `DUDUTT_TIMEOUT` | `30` | HTTP 超时（秒） |
| `DUDUTT_AUDIT_PATH` | `~/.dudutt/audit.jsonl` | 审计日志路径 |
| `DUDUTT_IDEMPOTENCY_TTL` | `600` | 幂等键有效期（秒） |
| `DUDUTT_KTT_STORAGE_STATE` | — | 浏览器后端：登录态文件 |
| `DUDUTT_KTT_SELECTORS` | — | 浏览器后端：选择器 JSON |
| `DUDUTT_BROWSER_HEADLESS` | `false` | 浏览器后端：无头模式 |

### 后端自动选择（`auto`）

1. 有 `CLIENT_ID` + `CLIENT_SECRET` → 用 `api`
2. 否则尝试 `browser`
3. 浏览器不可用则降级 `mock`（**每次降级都会在 stderr 明确告知**）

---

## 四、浏览器后端配置

用于官方 API 做不到的动作（**下架、改价**）。

```bash
pip install "dudutt[browser]"
python -m playwright install chromium

# 人工扫码登录一次（微信扫码，合规且稳定）
python -m dudutt.login --storage-state "C:/path/ktt_state.json"

export DUDUTT_BACKEND=browser
export DUDUTT_KTT_STORAGE_STATE="C:/path/ktt_state.json"
```

### 选择器校准（必做）

浏览器后端内置**防误操作护栏**：选择器未校准时，写操作会被**阻止**，
不会在你真实店铺里乱点。

校准步骤：

1. 打开快团团后台，F12 定位「下架」「改价」按钮等元素
2. 写入 JSON 文件（示例见下）
3. `export DUDUTT_KTT_SELECTORS="C:/path/selectors.json"`
4. 调用 `capabilities` 工具确认 `readiness.ready == true`

```json
{
  "goods_list_url": "https://ktt.pinduoduo.com/goods",
  "goods_row": ".goods-item",
  "delist_button": "button:has-text('下架')",
  "confirm_button": "button:has-text('确定')",
  "price_input": "input[name='price']"
}
```

> 为什么要求校准：选择器写错会导致**点错按钮**（如误删其他商品），
> 这是真实经营损失。宁可报错让你校准，也不静默乱点。

---

## 五、常见错误码速查

| 错误码 | 含义 | 解决 |
|---|---|---|
| `10001` | 公共参数错误 | 多为 timestamp 偏差超 10 分钟 |
| `10016` | client_id 不正确 | 核对 `DUDUTT_CLIENT_ID` |
| `10019` | access_token 过期 | 重新授权或用它 refresh |
| `20004` | **签名校验失败** | 核对 client_secret 与 MD5 大写 |
| `20005` | IP 不在白名单 | 控制台加 IP |
| `20031` | 无接口权限 | 控制台申请权限包 |
| `50001` | 业务错误 | 常因账号不是快团团商家 |
| `70036` | 应用测试状态限流 | 提交上线审核后解除 |

完整错误码见 <https://open.pinduoduo.com> 各接口文档底部。

---

## 六、上线检查清单

- [ ] 企业资质已认证
- [ ] 应用已创建，命名符合规范
- [ ] 所需权限包已全部勾选
- [ ] IP 白名单已配置（如需要）
- [ ] OAuth 授权完成，token 已写入环境变量
- [ ] `health_check` 返回 `ok: true`
- [ ] 用 `publish_goods(dry_run=true)` 验证参数组装
- [ ] 用小额测试团跑一次真实发布
- [ ] 审计日志路径确认可写
- [ ] 提交上线审核（解除测试状态调用限制）

---

## 七、安全提醒

- `DUDUTT_CLIENT_SECRET` 与 `access_token` **等同店铺操作权限**，
  不要提交进 Git、不要写进记忆系统、不要贴进聊天记录
- 建议为 dudutt 单独创建应用，权限最小化
- 定期检查审计日志 `~/.dudutt/audit.jsonl`，确认无异常写操作
