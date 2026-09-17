# 快团团 PC 后台完整功能地图

> **数据来源**：2026-09 对真实后台（`ktt.pinduoduo.com`）的只读扫描。
> 采集方式：遍历左侧导航菜单 + 点击采集路由 + URL 验证。
> **全程未提交任何表单、未改动任何数据。**
>
> 标记说明：✅ = 实测确认路由；🔗 = 点击后跳转外部地址；⏳ = 菜单可见但路由未采集

---

## 一、一级导航总览

登录后左侧共 **19 个一级入口**：

| # | 名称 | 类型 | 路由 | 说明 |
|---|---|---|---|---|
| 1 | **团购活动** | 单页 | `/groups` | 首页，团购列表与管理 |
| 2 | 我的店铺 | 单页 | ✅ `/mall` → `/settings/homepage` | 店铺装修/主页 |
| 3 | 商品库 | 单页 | ✅ `/goods_list` | 商品库管理 |
| 4 | 订单管理 | 子菜单 | 见 §3 | 5 个子项 |
| 5 | 违规信息 | 单页 | ✅ `/violation/list` | 违规记录 |
| 6 | 售后管理 | 子菜单 | 见 §4 | 2 个子项 |
| 7 | 商品核销 | 单页 | ✅ `/orders/verification` | 券码/核销 |
| 8 | 物流信息 | 子菜单 | 见 §5 | 5 个子项 |
| 9 | 团员管理 | 子菜单 | 见 §6 | 2 个子项 |
| 10 | 团长管理 | 子菜单 | 见 §7 | 1 个子项 |
| 11 | 资金中心 | 单页 | ✅ `/data/funds_home` | 资金/提现 |
| 12 | 营销工具 | 子菜单 | 见 §8 | 2 个子项 |
| 13 | 数据中心 | 子菜单 | 见 §9 | 2 个子项 |
| 14 | 供货商 | 子菜单 | ⏳（动态）| 供货商管理 |
| 15 | 客服数据 | 单页 | ✅ `/data/customer_service_admin` | 客服数据 |
| 16 | 企微助手 | 子菜单 | ✅ `/work_wechat/index` | 7 个子项 |
| 17 | 直播工具 | 单页 `NEW` | ⏳ | 直播相关 |
| 18 | 设置 | 子菜单 | 见 §10 | 7 个子项 |
| 19 | 功能反馈 | 单页 | ⏳ | 反馈入口 |

### 菜单 DOM 结构（关键）

```html
<li class="shell-menu-item" role="menuitem">          <!-- 单项（无子菜单）-->
  <span class="menu-title-name">团购活动</span>
</li>

<li class="shell-menu-submenu shell-menu-submenu-inline" role="menuitem">
  <div class="shell-menu-submenu-title" role="button"> <!-- 可展开的父级 -->
    <span class="menu-title-name">订单管理</span>
  </div>
  <ul class="shell-menu">
    <li class="shell-menu-item" role="menuitem">       <!-- 子项 -->
      <span class="menu-title-name">团购订单</span>
    </li>
  </ul>
</li>
```

**选中态**：`shell-menu-item-selected` / `shell-menu-item-active`

> ⚠️ 菜单项**没有 `href`**（纯 JS 路由），必须点击。
> 且点击可能**打开新标签页**（如打单工具），需检查 `context.pages()`。

---

## 二、团购活动 `/groups`（首页，最核心）

### 路由参数

```
/groups?page=1&status=-1&type=0&category=-1
```

| 参数 | 含义 |
|---|---|
| `page` | 页码 |
| `status` | 团状态（`-1`=全部）|
| `type` | 团购类型 |
| `category` | 分类 |

### 顶部操作

| 按钮 | 说明 |
|---|---|
| 查询 / 重置 | 筛选 |
| **一键开团** | **发布新团购** |
| 批量移动分类 | 批量改分类 |
| 批量编辑 | 批量编辑多个团 |
| 回收站 | 已删除的团（**可能可恢复**）|

### 筛选表单

| 筛选项 | 定位 |
|---|---|
| 团购类型 | `[data-testid="beast-core-select"]` |
| 团购发布时间 | `[data-testid="beast-core-rangePicker-htmlInput"]` |
| 团购结束时间 | 同上 |
| 团购分类 | `[data-testid="beast-core-select"]` |
| 团购搜索 | `[data-testid="beast-core-input-htmlInput"]`（placeholder「请输入团购名称搜索」）|
| 商品ID | 同上（placeholder「请输入商品ID搜索」）|

### 排序与分页

| 元素 | 定位 |
|---|---|
| 排序（综合/销量/上新）| `[data-testid="beast-core-radioGroup"]` |
| 分页 | `[data-testid="beast-core-pagination"]` |

### 团卡片信息

```
[团购标题]              ← [data-testid="beast-core-ellipsis"]
¥39~169                 ← 价格区间
已开启帮卖团
佣金¥7.8~29.8           ← 帮卖佣金
2026.09.04              ← 创建日期
0.00 / 实际收入(元)
0 / 已跟团
4 / 已浏览
团数据详情 | 手机查看 | 订单管理 | 团管理
[状态：跟团中 / 已结束]
```

### 团状态码（官方 API 对应）

| 值 | 含义 |
|---|---|
| `-10` | 待发布（预览团）|
| `-5` | 未开始 |
| `1` | 跟团中 |
| `20` | 已结束 |
| `30` | 已删除 |

---

## 三、「团管理」菜单（⭐ 最核心）

点击任意团卡片的 **`团管理`** 弹出，共 **10 项**：

| 菜单项 | 功能 | 风险 | 官方 API |
|---|---|---|---|
| 关联供货商 | 关联供货商 | 🟢 | ❌ 无 |
| 帮卖团长管理 | 管理帮卖 | 🟡 | ❌ 无 |
| **修改团信息** | **改价 / 改库存 / 改标题** | 🟡 | ❌ 无 |
| **结束团** | **下架（停止售卖）** | 🔴 **不可逆** | ❌ 无 |
| 复制团 | 以该团为模板新建 | 🟢 | ❌ 无 |
| **删除团** | **彻底删除** | 🔴 **最危险** | ❌ 无 |
| 隐藏团 | 从列表隐藏 | 🟢 | ❌ 无 |
| 标记团 | 打标记 | 🟢 | ❌ 无 |
| 置顶 | 列表置顶 | 🟢 | ❌ 无 |
| 查看操作记录 | 查看历史操作 | 🟢 只读 | ❌ 无 |

**这 10 项官方 API 一个都没有** —— 这是浏览器路径的核心价值。

### 定位方式

```python
# 1. 先点开菜单
page.get_by_text("团管理", exact=True).first.click()

# 2. 再点菜单项
page.get_by_text("修改团信息", exact=True).first.click()
page.get_by_text("结束团", exact=True).first.click()

# 3. 关闭菜单
page.keyboard.press("Escape")
```

---

## 四、订单管理

| 子项 | 路由 | 说明 |
|---|---|---|
| 团购订单 | ✅ `/orders/order_list` | 团购产生的订单 |
| 店铺订单 | ⏳ `/orders/shop_order*` | 店铺订单 |
| 积分商城订单 | ✅ `/orders/integral_order_list` | 积分兑换订单 |
| 本地生活订单 | ✅ `/orders/local_life/order_list` | 本地生活业务 |
| 团单管理 | ✅ `/orders/group_order/list` | 团单管理 |

**父级定位**：`div.shell-menu-submenu-title` 文字为「订单管理」

---

## 五、售后管理

| 子项 | 路由 | 说明 |
|---|---|---|
| 批量退款 | ✅ `/orders/batch_refund` | 批量退款 |
| 待处理售后 | ⏳ | 售后工单 |

---

## 六、物流信息

| 子项 | 路由 | 说明 |
|---|---|---|
| 自提点管理 | ⏳ | 自提点配置 |
| 配送路线 | ✅ `/orders/distribution_route/list` | 配送路线 |
| 快递电子面单 | 🔗 `/print/pendingOrder`（打单工具，**新标签页**）| 电子面单 |
| 包裹中心 | ⏳ | 包裹追踪 |
| 团员改地址 | ⏳ | 地址修改申请 |

---

## 七、团员 / 团长管理

| 所在菜单 | 子项 | 路由 |
|---|---|---|
| 团员管理 | 我的团员 | ✅ `/members/list` |
| 团员管理 | 团员运营 | ✅ `/data/crm` |
| 团长管理 | 我的团长 | ✅ `/owners/list` |

---

## 八、营销工具

| 子项 | 路由 | 说明 |
|---|---|---|
| 会员管理 | ✅ `/vip/setting` | 会员体系配置 |
| 积分商城 | ✅ `/score/first_guide` | 积分商城 |

---

## 九、数据中心 & 资金

| 所在菜单 | 子项/页面 | 路由 |
|---|---|---|
| 资金中心 | （单项）| ✅ `/data/funds_home` |
| 数据中心 | 数据分析 | ⏳ |
| 数据中心 | 数据报表 | ⏳ |
| 客服数据 | （单项）| ✅ `/data/customer_service_admin` |

---

## 十、企微助手

父级首页：✅ `/work_wechat/index`

| 子项 | 路由 |
|---|---|
| 客户画像 | ⏳ |
| 话术库 | ⏳ |
| 员工活码 | ⏳ |
| 账号管理 | ⏳ |
| 绑定团长 | ⏳ |
| 应用管理 | ⏳ |
| 操作权限 | ⏳ |

---

## 十一、设置

| 子项 | 路由 | 说明 |
|---|---|---|
| 账户管理 | ✅ `/identity/license_detail` | 资质信息 |
| 主页设置 | ✅ `/setting/home` | 店铺主页 |
| 团购设置 | ✅ `/setting/group` | 团购默认设置 |
| 订单设置 | ✅ `/orders/order_setting` | 订单相关设置 |
| 通知设置 | ⏳ | 消息通知 |
| 店铺设置 | ⏳ | 店铺信息 |
| 二维码设置 | ⏳ | 二维码 |

---

## 十二、其他已确认页面

| 页面 | 路由 | 说明 |
|---|---|---|
| 我的店铺（重定向后）| ✅ `/settings/homepage` | 店铺主页 |
| 商品库（重定向后）| ✅ `/settings/group` | 注意：会重定向 |
| 违规信息（重定向后）| ✅ `/settings/order` | 注意：会重定向 |
| 商品核销 | ✅ `/orders/verification` | 券码核销 |
| 打单工具 | ✅ `/print/pendingOrder` | 独立标签页 |
| 登录页 | `/login` | 微信扫码 |

---

## 十三、`data-testid` 稳定标识清单（实测）

后台基于拼多多 **Beast 设计系统**，开放了供自动化使用的稳定标识：

| testid | 用途 |
|---|---|
| `beast-core-button` | 所有按钮 |
| `beast-core-ellipsis` | 团购标题（长文本省略）|
| `beast-core-input-htmlInput` | 文本输入框 |
| `beast-core-select` | 下拉选择 |
| `beast-core-select-htmlInput` | 下拉输入框 |
| `beast-core-rangePicker-input` | 日期区间 |
| `beast-core-rangePicker-htmlInput` | 日期区间输入框 |
| `beast-core-icon-calendar` | 日历图标 |
| `beast-core-radioGroup` | 单选组（排序）|
| `beast-core-radio` / `beast-core-radio-radioIcon` | 单选项 |
| `beast-core-table` / `-middle-header` / `-middle-thead` / `-th` / `-middle-body` / `-middle-tbody` | 表格结构 |
| `beast-core-pagination` | 分页 |
| `beast-core-drawer` / `beast-core-drawer-content` | 抽屉（智能助手）|
| `beast-core-portal` / `beast-core-portal-main` | 浮层容器 |
| `beast-core-popover-trigger-wrapper` | 气泡触发器 |
| `beast-core-badge` | 徽标（消息数）|
| `beast-core-icon-close` | 关闭图标 |
| `beast-core-icon-plus-circle_filled` | 加号图标（一键开团）|
| `beast-core-icon-menu-unfold` | 菜单展开 |
| `beast-core-grid-row` / `-grid-col-wrapper` | 栅格 |
| `beast-core-form-item` | 表单项 |
| `beast-core-spin` / `-spin-mask` | 加载中 |
| `beast-core-switch` | 开关 |
| `beast-core-divider` | 分隔线 |
| `beast-core-button-link` | 链接式按钮 |

> **`.beast-core-*` 是 Google 风格的组件类名，相对稳定；但真正的保险是 `data-testid`。**

---

## 十四、弹窗与遮挡层（必读）

后台会**反复出现**遮挡层，导致点击失效。

| 弹窗 | 特征 | 关闭方式 |
|---|---|---|
| 智能助手抽屉 | `[data-testid="beast-core-drawer"]`，内容「上午好，XXX」| 关闭图标 / `Escape` |
| 置顶管理 | 标题「管理置顶团购」，有「确定」「取消」| 点 `取消` |
| 消息分流提示 | 「打开消息页面，才可保证消息正常分流」| 关闭图标 |
| 通知提示 | 「知道了」按钮 | 点 `知道了` |

### 标准清理函数

```python
def dismiss_popups(page):
    """关闭所有可见遮挡层。只用无害操作，绝不点"确定"。"""
    for text in ("知道了", "取消"):
        try:
            btn = page.get_by_text(text, exact=True).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=2000)
                page.wait_for_timeout(400)
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
```

> ⚠️ 只点 `取消` / `知道了` / `Escape` / 关闭图标。
> **绝不点 `确定`** —— 可能提交未知变更。

---

## 十五、常见任务 → 路由速查

| 任务 | 去哪 |
|---|---|
| 看团购列表 | `/groups` |
| 发布新团 | `/groups` → 一键开团 |
| 下架/结束团 | `/groups` → 团管理 → 结束团 |
| 改价 | `/groups` → 团管理 → 修改团信息 |
| 删团 | `/groups` → 团管理 → 删除团（🔴）|
| 找回误删的团 | `/groups` → 回收站 |
| 看商品库 | `/goods_list` |
| 看订单 | `/orders/order_list` |
| 批量退款 | `/orders/batch_refund` |
| 看资金 | `/data/funds_home` |
| 看团员 | `/members/list` |
| 看违规 | `/violation/list` |
| 核销券码 | `/orders/verification` |
| 打单 | `/print/pendingOrder`（独立标签）|
| 店铺设置 | `/setting/home` / `/setting/group` |
| 订单设置 | `/orders/order_setting` |

---

## 十六、后台内部接口（**严禁直接调用**）

网络面板可见的后台自身接口：

```
/api/ktt_gateway/user/mall/check_account
/api/ktt_gateway/user/info/personal_center
/api/ktt_gateway/user_permission/query_permission_after_proxy
/api/ktt_group/activity_query/query_top_activity_list
/api/ktt_group/activity_feeds/query_for_personal_center
/api/ktt_group/activity_category/query_category_list
/api/ktt_gateway/common/gray_config/query
/api/cupid/query_qr_code          （登录二维码）
/api/cupid/login/check_qr_code    （登录轮询）
```

> 🔴 **严禁伪造请求调用**。
> 这些是**内部私有接口**，非官方开放 API。
> 直接调用属于逆向行为，明确违反平台协议，是风控重点打击对象，
> **可能导致账号封禁**。
>
> **本技能只通过真实浏览器点击操作页面。**

---

## 十七、重新侦察方法（后台改版后）

```javascript
// 1. 收集所有菜单项
[...document.querySelectorAll('li.shell-menu-item, li.shell-menu-submenu')]
  .map(li => (li.innerText||'').trim().split('\n')[0])

// 2. 收集所有 data-testid
[...document.querySelectorAll('[data-testid]')]
  .map(e => e.getAttribute('data-testid'))

// 3. 读当前路由
location.href

// 4. 点击采集路由（⚠️ 只点纯导航项，绝不点"结束团/删除团/确定"）
```

### 侦察红线

| 可以点 | 绝不能点 |
|---|---|
| 左侧导航菜单项 | 结束团 / 删除团 |
| 团管理（只弹菜单）| 弹窗的「确定」|
| 查询 / 重置 | 任何提交类按钮 |
| 关闭类（取消/知道了）| 批量操作按钮 |
