# 动作 ↔ 官方接口映射与能力边界

本文档是 dudutt 的**能力真相来源**。所有接口信息均来自拼多多开放平台官方文档逐条核实
（<https://open.pinduoduo.com>，2026-09 核对），并与
[niltor/open-pdd-net-sdk](https://github.com/niltor/open-pdd-net-sdk) 的 `KttApi.cs` 交叉验证。

---

## 一、核心结论：能力边界

| 你要的功能 | 官方 API | 变通 / 替代 |
|---|---|---|
| **发布商品** | ✅ `pdd.ktt.group.create` | — |
| **改库存** | ✅ `pdd.ktt.goods.incr.quantity` | — |
| **下架商品** | ❌ **无此接口** | api 后端：库存全量归零（≈售罄）<br>browser 后端：真实下架 |
| **改价** | ❌ **无此接口** | browser 后端：真实改价<br>或：下架后重建团 |

### 为什么没有「下架」和「改价」

官方 KTT 接口共 **36 个**（已逐条核对），覆盖商品、团购、订单、售后、物流、供货商。
但：

- **没有触发团删除的接口**。团状态里有 `30:已删除`，但没有 API 能让它变成这个状态。
- **没有修改价格的接口**。价格在创建团购时确定，此后锁死。

这不是文档没找到，而是**确实不存在**。因此 dudutt 用两个互补后端覆盖：

```
api 后端      → 官方支持的动作（稳定、合规）
browser 后端  → 官方缺失的动作（下架、改价）
```

---

## 二、动作详细映射

### 2.1 发布商品 → `pdd.ktt.group.create`

- **接口**：`pdd.ktt.group.create`（快团团创建团购接口）
- **限流**：500 次/秒
- **授权**：必须用户授权
- **权限包**：快团团团购管理权限包

**主要参数**（来自官方文档）：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | STRING | ✅ | 团购标题 |
| `start_time` | LONG | ✅ | 开始时间戳（毫秒） |
| `end_time` | LONG | ✅ | 结束时间戳（毫秒），不能早于开始时间或当前时间 |
| `goods_list` | OBJECT[] | ✅ | 开团商品列表，不能为空 |
| `is_save_preview` | INTEGER | ✅ | 0=直接发布，1=**保存为预览团** |
| `isv_no` | STRING | ❌ | 分配给 isv 的编号，用于绑新 |

**`goods_list` 每项**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `goods_name` | STRING | ✅ | 商品名 |
| `category_name` | STRING | ✅ | 分类名 |
| `goods_desc` | STRING | ✅ | 商品描述 |
| `sku_list` | OBJECT[] | ✅ | SKU 列表 |
| `pic_url_list` | STRING[] | ❌ | 商品图，**不超过 20 张** |
| `market_price` | LONG | ❌ | 划线价（分），0=无 |
| `limit_buy` | INTEGER | ❌ | 限购数，0=不限购 |

**`sku_list` 每项**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `price_in_fen` | LONG | ✅ | 价格，单位**分** |
| `quantity_type` | INTEGER | ✅ | 0=普通，1=无限（忽略 total_quantity） |
| `total_quantity` | LONG | ✅ | 总库存，**最大 100 万** |
| `spec_id_list` | LONG[] | ✅ | 规格 ID 列表，无规格传 `[]` |
| `thumbnail` / `thumb_url` | STRING | ❌ | SKU 图，须 jpg/jpeg/png，≤1200×1200，≤1MB |
| `external_sku_id` | STRING | ❌ | 外部商品编码，≤32 位 |

**返回**：`activity_no`（团号，用于查询创建结果）、`success`

**异步特性**：创建是异步的。dudutt 在创建后会自动回查
`pdd.ktt.group.query.status`，让调用方知道是否真的建成了。

---

### 2.2 改库存 → `pdd.ktt.goods.incr.quantity`

- **接口**：`pdd.ktt.goods.incr.quantity`（快团团ERP增加商品库存接口）
- **限流**：2500 次/秒

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `goods_id` | LONG | ✅ | 商品 ID |
| `sku_id` | LONG | ✅ | SKU ID |
| `quantity_delta` | INTEGER | ✅ | 库存增减值 |
| `modify_quantity_type` | INTEGER | ❌ | **不传或 1=增量修改，2=全量修改** |

dudutt 默认 `modify_quantity_type=2`（全量设置），更符合直觉。
需要「减 5 件」时传 `1` + `quantity=-5`。

---

### 2.3 下架商品 → ❌ 无接口

- **官方**：无。
- **api 后端变通**：把该商品**全部 SKU 库存全量置 0**。
  - 效果：商品仍存在，但无法购买（≈售罄）
  - 返回体 `method` 字段为 `workaround_stock_zero`，`caveat` 说明副作用
- **browser 后端**：真实点击后台「下架」按钮

> 为什么不在 api 后端"假装下架"：
> 库存归零与真正下架**不等价**（商品仍可见、仍可能被搜索到）。
> 必须在返回体里如实标明，让调用方知道实际发生了什么。

---

### 2.4 改价 → ❌ 无接口

- **官方**：无。价格在创建团购时确定后锁死。
- **api 后端**：返回 `unsupported: true`，附带替代方案
- **browser 后端**：真实修改后台价格
- **另一种方案**：下架当前团 → 用新价格重新创建

---

## 三、辅助接口（已封装到商品/团管理）

| 动作 | 接口 | 说明 |
|---|---|---|
| 团列表 | `pdd.ktt.group.query.list` | **起止时间差不能超过 7 天** |
| 团创建结果 | `pdd.ktt.group.query.status` | 用 `activity_no` 查 |
| 商品列表 | `pdd.ktt.goods.query.list` | 分页 |
| 单品详情 | `pdd.ktt.goods.query.single` | 按 `goods_id` |
| 创建规格 | `pdd.ktt.goods.create.spec` | 返回 `spec_id` 供建团用；规格乘积 ≤400 |
| 上传商品图 | `pdd.ktt.goods.upload.image` | **480~1200 正方形、<1MB**；10 次/秒；同一 URL 不可并发 |
| 上传团图片 | `pdd.ktt.group.upload.image` | — |

### 团状态码

| 值 | 含义 |
|---|---|
| `-10` | 待发布（预览团） |
| `-5` | 未开始 |
| `1` | 跟团中 |
| `20` | 已结束 |
| `30` | 已删除 |

---

## 四、全部 36 个 KTT 官方接口

用 `list_official_apis` 工具可随时查询（支持关键词过滤）。

### 商品 / 团购（8）
- `pdd.ktt.group.create` —— 创建团购
- `pdd.ktt.group.query.list` —— 团列表
- `pdd.ktt.group.query.status` —— 创建结果
- `pdd.ktt.group.upload.image` —— 上传团图片
- `pdd.ktt.goods.create.spec` —— 创建规格
- `pdd.ktt.goods.incr.quantity` —— 增改库存
- `pdd.ktt.goods.query.list` —— 商品列表
- `pdd.ktt.goods.query.single` —— 单品查询
- `pdd.ktt.goods.upload.image` —— 上传商品图

### 订单 / 售后 / 物流（11）
- `pdd.ktt.order.list` —— 订单列表
- `pdd.ktt.order.get` —— 订单详情
- `pdd.ktt.increment.order.query` —— 增量查订单
- `pdd.ktt.order.refund.get` —— 售后单
- `pdd.ktt.order.logistic.create` —— 物流发布
- `pdd.ktt.order.logistic.delete` —— 物流删除
- `pdd.ktt.order.voucher.sync` —— 券码同步
- `pdd.ktt.order.voucher.verify` —— 券码核销
- `pdd.ktt.after.sales.increment.list` —— 增量售后单
- `pdd.ktt.help.sell.query.commission` —— 帮卖分佣查询
- `pdd.ktt.user.site.pagequery` —— 自提点查询

### 供货商（16）
- `pdd.ktt.purchase.goods.cat.info` —— 商品分类查询
- `pdd.ktt.purchase.goods.create` —— 商品创建
- `pdd.ktt.purchase.goods.supplier.brand.info` —— 品牌查询
- `pdd.ktt.purchase.supplier.goods.info` —— 商品查询
- `pdd.ktt.purchase.supplier.storage.update` —— 库存编辑
- `pdd.ktt.purchase.order.list` / `.info` / `.delivery` —— 订单列表/详情/发货
- `pdd.ktt.purchase.order.after.sales.list` —— 售后列表
- `pdd.ktt.purchase.order.logistic.replace` —— 运单号替换
- `pdd.ktt.purchase.sample.order.list` / `.info` / `.delivery` —— 拍样品订单
- `pdd.ktt.purchase.sample.order.logistic.replace` —— 拍样品运单号修改
- `pdd.ktt.order.merge.ship.order.group` —— 团长合并发货订单分组
- `pdd.ktt.purchase.order.merge.ship.order.group` —— 供货商合并发货订单分组

---

## 五、网关与签名

```
网关：https://gw-api.pinduoduo.com/api/router   （全部 POST）
签名：MD5(client_secret + 排序拼接(params) + client_secret).upper()
拼接：按参数名字典序，格式 key1value1key2value2（无分隔符）
时间戳：秒级，需与服务器时间差在 10 分钟内
```

**易错点**（dudutt 已处理并有测试锁定）：

1. 签名结果必须**转大写**
2. `bool` 要转成 `true`/`false`（Python 的 `str(True)` 是 `"True"`，会签名错）
3. 复杂类型（dict/list）要序列化为**紧凑 JSON**，且签名用同一份文本
4. `sign` 字段自身必须从待签参数中剔除
5. 值为 `None` 的参数必须剔除

---

## 六、未封装但可用的能力

dudutt 目前聚焦「商品管理」四动作。以下能力官方有接口但**尚未封装**，
可用 `list_official_apis` 查到接口名后按需扩展：

- 订单拉取与详情
- 售后处理
- 物流发布/删除
- 券码同步与核销
- 供货商侧全套（商品、订单、拍样品）
