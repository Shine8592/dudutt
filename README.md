# dudutt

快团团（拼多多旗下社群团购）网店管理 MCP 服务 —— 让 AI Agent 直接发布商品、下架商品、改价改库存。

> **架构定位**：官方 POP API 为主，浏览器自动化兜底，双后端可插拔。
> 当官方接口不支持某动作（如「下架」「改价」）时，自动降级到浏览器后端或给出明确的能力提示，**绝不假装成功**。

## 为什么需要它

| 现状 | 说明 |
|---|---|
| 快团团 API 藏在拼多多开放平台 | 接口散落在 `open.pinduoduo.com`，无统一 SDK |
| 官方无「下架 / 改价」接口 | 只能靠库存归零 / 重建团变通，或走浏览器后台 |
| 出错代价高 | 商品误下架、价格误改直接影响真实经营 |

`dudutt` 把上述复杂度收敛成 MCP 工具，并内置**能力协商**与**写操作护栏**。

## 快速开始

```bash
pip install dudutt            # 仅官方 API 后端
pip install "dudutt[browser]" # 额外支持浏览器兜底
```

### 配置凭据

```bash
# 官方 API 后端（推荐，需企业资质）
export DUDUTT_CLIENT_ID="your_client_id"
export DUDUTT_CLIENT_SECRET="your_client_secret"
export DUDUTT_ACCESS_TOKEN="your_access_token"

# 或使用 mock 后端跑通流程（无需凭据）
export DUDUTT_BACKEND="mock"
```

### 挂载到 MCP 客户端

```jsonc
{
  "mcp": {
    "dudutt": {
      "type": "local",
      "command": ["python", "-u", "-m", "dudutt"],
      "environment": {
        "DUDUTT_CLIENT_ID": "{env:DUDUTT_CLIENT_ID}",
        "DUDUTT_CLIENT_SECRET": "{env:DUDUTT_CLIENT_SECRET}",
        "DUDUTT_ACCESS_TOKEN": "{env:DUDUTT_ACCESS_TOKEN}"
      }
    }
  }
}
```

## 工具一览

| 工具 | 动作 | 官方 API | 浏览器兜底 |
|---|---|---|---|
| `capabilities` | 查询当前后端支持哪些动作 | — | — |
| `list_groups` | 团列表 | ✅ | ✅ |
| `list_goods` / `get_goods` | 商品列表 / 单品 | ✅ | ✅ |
| `publish_goods` | **发布商品**（创建团购） | ✅ | ✅ |
| `set_stock` | **改库存** | ✅ | ✅ |
| `delist_goods` | **下架商品** | ❌ 库存归零变通 | ✅ |
| `update_price` | **改价** | ❌ 需重建团 | ✅ |
| `audit_log` | 查看写操作审计 | — | — |

## 安全设计

- **能力协商**：先查 `capabilities`，后端不支持时明确报错，不给幻觉结果
- **dry-run 预演**：写操作默认返回"将要发生什么"，确认后才真正执行
- **审计日志**：每次写操作落盘 JSONL，可追溯
- **幂等键**：同一 `idempotency_key` 重复调用不会重复下单

## 文档

- [docs/SETUP.md](docs/SETUP.md) —— 企业资质申请与授权全流程
- [docs/API-MAP.md](docs/API-MAP.md) —— 动作 ↔ 官方接口映射与能力边界

## License

MIT
