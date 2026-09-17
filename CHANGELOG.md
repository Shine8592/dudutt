# 变更记录

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-09-17

### 新增

- **POP 网关客户端**（`pop_client.py`）
  - MD5 签名算法（含易错点的正确处理：大写、bool→true/false、紧凑 JSON、剔除 None 与 sign）
  - 统一请求封装与响应解包
  - 30+ 官方错误码的中文可执行建议映射

- **三后端可插拔架构**（`backends/`）
  - `api`：官方 POP API，覆盖发布商品与改库存
  - `browser`：Playwright 浏览器兜底，覆盖官方缺失的**下架**与**改价**
  - `mock`：内存模拟后端，无需凭据即可跑通全流程
  - `auto`：按凭据可用性自动选择并明确告知降级

- **能力协商机制**（`Support` 层次）
  - 每个后端的每个动作如实声明：`native` / `workaround` / `none`
  - 不支持时返回 `unsupported: true` 并附替代方案，**绝不假装成功**

- **业务动作层**（`actions.py`）
  - `publish_goods`：发布商品（创建团购），含完整参数校验
  - `set_stock`：改库存（增量 / 全量）
  - `delist_goods`：下架（api 后端为库存归零变通，返回体标明 `method`）
  - `update_price`：改价（api 后端明确返回 unsupported）
  - `list_groups` / `list_goods` / `get_goods`：只读查询

- **安全护栏**
  - 写操作默认 `dry_run=true`，先预演后执行
  - 幂等键（默认 10 分钟窗口）防止重复建团
  - JSONL 审计日志记录每次写操作

- **MCP 工具层**（`server.py`）
  - 11 个工具，含 `capabilities`（能力查询）与 `list_official_apis`（36 个官方接口清单）

- **测试**（89 项，全部无需联网）
  - `test_pop_client.py`：签名、参数组装、响应解包、错误码（32 项）
  - `test_actions.py`：能力协商、dry-run、幂等、参数校验、变通下架（39 项）
  - `test_e2e_mcp.py`：真实拉起 stdio server 走完整协议（18 项）

- **文档**
  - `docs/SETUP.md`：企业资质申请与授权全流程
  - `docs/API-MAP.md`：动作 ↔ 官方接口映射与能力边界

### 已知限制

- **官方 API 无「下架」与「改价」接口** —— 这是平台限制，非本项目缺陷。
  前者在 api 后端以库存归零变通，后者需浏览器后端或重建团。
- 浏览器后端为**骨架 + 护栏**，页面选择器需在真实账号环境校准后使用；
  未校准时写操作会被主动阻止（避免误操作真实店铺）。
- 仅覆盖商品管理四动作；订单、售后、物流、供货商接口已登记但未封装。
