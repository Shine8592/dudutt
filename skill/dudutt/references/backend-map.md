# 快团团 PC 后台结构地图

> 本文档由**真实后台侦察**得出（2026-09，仅只读操作，未改动任何数据）。
> 用途：让 Agent 知道往哪里点，而不是靠猜。

---

## 一、基础信息

| 项 | 值 |
|---|---|
| 后台域名 | `https://ktt.pinduoduo.com` |
| 团购列表 | `/groups` |
| 登录页 | `/login`（未登录时自动跳转）|
| 前端框架 | 拼多多 **Beast 设计系统**（`beast-core-*`）|
| 登录方式 | 微信扫码（`/api/cupid/query_qr_code` + `login/check_qr_code` 轮询）|

### 重要：`data-testid` 是稳定锚点

后台为自动化测试开放了 `data-testid` 属性，**不随样式改版失效**。
**优先用它定位元素**，而不是 hash 类名。

```python
# ✅ 推荐
page.locator('[data-testid="beast-core-button"]').filter(has_text="查询")
page.locator('[data-testid="beast-core-ellipsis"]')

# ❌ 禁止（发版即失效）
page.locator('.BTN_gray_15w5x36')   # hash 后缀会变
```

---

## 二、团购列表页 `/groups`

### 2.1 页面参数

```
/groups?page=1&status=-1&type=0&category=-1
```

URL 参数可用于筛选：

| 参数 | 含义 |
|---|---|
| `page` | 页码 |
| `status` | 团状态（`-1` = 全部）|
| `type` | 团购类型 |
| `category` | 分类 |

### 2.2 顶部操作区

| 元素 | 定位 |
|---|---|
| 查询 | `[data-testid="beast-core-button"]` + 文字「查询」|
| 重置 | 同上，文字「重置」|
| **一键开团** | 文字「一键开团」；其父元素类名 `Header_customButton__PJfFF` |
| 批量移动分类 | 文字锚定 |
| 批量编辑 | 文字锚定 |
| 回收站 | 文字锚定 |

**「一键开团」的实测 DOM**：

```html
<div class="Header_customButton__PJfFF">
  <i data-testid="beast-core-icon-plus-circle_filled"
     class="ICN_outerWrapper_15w5x36 ICN_type-plus-circle_filled_15w5x36"
     style="margin-right: 4px;"></i>
  <span>一键开团</span>
</div>
```

> 注意：它**不是 `<a>` 标签**，没有 href，是个带 JS 事件的 div。
> 必须用文字或 testid 定位，不能靠 href。

### 2.3 筛选表单

| 筛选项 | 定位 |
|---|---|
| 团购类型 | `[data-testid="beast-core-select"]` |
| 团购发布时间 | `[data-testid="beast-core-rangePicker-htmlInput"]` |
| 团购结束时间 | 同上（第二个）|
| 团购分类 | `[data-testid="beast-core-select"]` |
| 团购搜索 | `[data-testid="beast-core-input-htmlInput"]`，placeholder「请输入团购名称搜索」|
| 商品ID | 同上，placeholder「请输入商品ID搜索」|

### 2.4 团购卡片

每张卡片包含（文字顺序）：

```
[团购标题]
¥39~169                          ← 价格区间
已开启帮卖团
佣金¥7.8~29.8                    ← 帮卖佣金
2026.09.04                       ← 创建日期
0.00 / 实际收入(元)
0 / 已跟团
4 / 已浏览
团数据详情 | 手机查看 | 订单管理 | 团管理
[状态：跟团中 / 已结束]
```

| 元素 | 定位 |
|---|---|
| 团购标题 | `[data-testid="beast-core-ellipsis"]` |
| 状态标签 | 卡片内文字「跟团中」「已结束」|
| 底部操作按钮 | 文字锚定：`团数据详情` / `手机查看` / `订单管理` / `团管理` |

### 2.5 排序与分页

| 元素 | 定位 |
|---|---|
| 排序（综合/销量/上新）| `[data-testid="beast-core-radioGroup"]` |
| 分页 | `[data-testid="beast-core-pagination"]` |

---

## 三、「团管理」菜单（核心）

点击卡片下的 **`团管理`** 后弹出的菜单项（**实测完整清单**）：

```
关联供货商
帮卖团长管理
修改团信息      ← 改价 / 改库存 / 改标题
结束团          ← 下架（🔴 不可逆）
复制团
删除团          ← 彻底删除（🔴 不可逆）
隐藏团
标记团
置顶
查看操作记录
```

### 定位方式

```python
# 1. 先点开菜单
page.get_by_text("团管理", exact=True).first.click()

# 2. 再点菜单项
page.get_by_text("修改团信息", exact=True).first.click()
page.get_by_text("结束团", exact=True).first.click()
```

### 菜单关闭

```python
page.keyboard.press("Escape")
# 或点击页面空白处
```

---

## 四、弹窗与遮挡层（必读）

后台会**反复出现**遮挡层，导致后续点击失效。**每次操作前先清理**。

### 4.1 智能助手抽屉

```
[data-testid="beast-core-drawer"]
[data-testid="beast-core-drawer-content"]
内容： "智能助手 / 上午好，XXX / 我是您的快团团助手..."
```

**关闭**：点抽屉右上角关闭图标（`[data-testid="beast-core-icon-close"]`），
或按 `Escape`。

### 4.2 置顶管理弹窗

```
标题：管理置顶团购
提示：系统仅保留最新置顶的20个团购，其他团购已自动取消置顶。
按钮：确定 / 取消
```

**关闭**：点 `取消` 或 `知道了`。

### 4.3 消息分流提示

```
文字：打开消息页面，才可保证消息正常分流
```

**关闭**：点其关闭图标。

### 4.4 标准清理函数（建议）

```python
def dismiss_popups(page):
    """关闭所有可见的遮挡弹窗。无害操作，可安全重复调用。"""
    for text in ("知道了", "取消"):
        try:
            btn = page.get_by_text(text, exact=True).first
            if btn.is_visible(timeout=1000):
                btn.click(timeout=2000)
                page.wait_for_timeout(500)
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass
```

> ⚠️ 只点 `取消` / `知道了` / `Escape` / 关闭图标 ——
> **绝不点 `确定`**（可能提交未知变更）。

---

## 五、后台内部接口（仅供参考，**不要直接调用**）

以下是通过网络面板观察到的后台自身接口，**仅供理解页面行为**：

```
POST /api/ktt_gateway/user/mall/check_account
POST /api/ktt_gateway/user/info/personal_center
POST /api/ktt_group/activity_query/query_top_activity_list
POST /api/ktt_group/activity_feeds/query_for_personal_center
POST /api/ktt_group/activity_category/query_category_list
POST /api/ktt_gateway/user_permission/query_permission_after_proxy
```

> 🔴 **严禁伪造请求直接调用这些接口**。
> 它们是**内部私有接口**，非官方开放 API。直接调用属于逆向行为，
> 明确违反平台协议，是风控重点打击对象，可能导致账号封禁。
> **本技能只通过真实浏览器点击操作页面。**

---

## 六、已知不稳定因素

| 风险 | 表现 | 应对 |
|---|---|---|
| 页面改版 | 元素找不到 | 优先 `data-testid`；失效则重新侦察 |
| 弹窗遮挡 | 点击无反应 | 先执行 `dismiss_popups()` |
| 加载延迟 | 元素未就绪 | 操作间加 `wait_for_timeout`，或用 `wait_for_selector` |
| hash 类名 | 类名带随机后缀 | **禁用**，改用 testid 或文字 |
| 登录过期 | 跳转 `/login` | 请用户重新扫码 |

---

## 七、重新侦察的方法

后台改版后，按此流程重新采集选择器（**全程只读**）：

```javascript
// 1. 收集所有 data-testid
[...document.querySelectorAll('[data-testid]')].map(e => ({
  id: e.getAttribute('data-testid'),
  text: (e.innerText || '').trim().slice(0, 40)
}))

// 2. 找可交互按钮的文字
[...document.querySelectorAll('button, [class*="BTN_"], [class*="Btn"]')]
  .map(b => b.innerText.trim()).filter(Boolean)

// 3. 抓页面可见文字（了解结构）
document.body.innerText
```

> 侦察时**只读**：不要点击任何会提交数据的按钮。
> `团管理` 这类只弹菜单不提交的可以点；`结束团` / `删除团` / `确定` 绝对不能点。
