#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快团团（KTT）官方接口注册表。

来源：拼多多开放平台官方文档逐条核实（open.pinduoduo.com），
并与 niltor/open-pdd-net-sdk 的 KttApi.cs 交叉验证。

为什么把接口清单写成代码而不是散在文档里：
Agent 需要**机器可读**的能力边界。写成注册表后，
`capabilities` 工具才能如实回答"这个动作能不能做"，
而不是让模型凭印象猜（幻觉高发区）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 网关公共说明（所有接口共用）
GATEWAY = "https://gw-api.pinduoduo.com/api/router"
AUTH_MODE_USER = "必须用户授权"
AUTH_MODE_NONE = "不需用户授权"


@dataclass(frozen=True)
class KttApi:
    """一个官方接口的元数据。"""

    name: str  # 接口名，如 pdd.ktt.group.create
    label: str  # 中文名
    purpose: str  # 用途说明
    auth: str = AUTH_MODE_USER  # 授权模式
    rate_limit: str = "2500次/1秒"  # 官方限流
    note: str = ""  # 附加说明（尤其是限制）


# ---------------------------------------------------------------------------
# 商品 / 团购（本项目的核心动作所依赖）
# ---------------------------------------------------------------------------

API_GROUP_CREATE = KttApi(
    name="pdd.ktt.group.create",
    label="快团团创建团购接口",
    purpose="创建团购，等同「发布商品」",
    rate_limit="500次/1秒",
    note=(
        "团创建后价格即生效且官方未开放修改；"
        "is_save_preview=1 可先存为预览团（不公开），确认后再发布。"
    ),
)

API_GROUP_QUERY_LIST = KttApi(
    name="pdd.ktt.group.query.list",
    label="快团团查询团列表接口",
    purpose="按更新时间分页查询团列表",
    note="起止时间差不能超过 7 天。",
)

API_GROUP_QUERY_STATUS = KttApi(
    name="pdd.ktt.group.query.status",
    label="快团团查询团购创建结果接口",
    purpose="用 activity_no 查询团购创建结果",
)

API_GROUP_UPLOAD_IMAGE = KttApi(
    name="pdd.ktt.group.upload.image",
    label="快团团上传图片接口",
    purpose="上传团购相关图片",
)

API_GOODS_CREATE_SPEC = KttApi(
    name="pdd.ktt.goods.create.spec",
    label="快团团商品规格创建接口",
    purpose="创建商品规格，返回 spec_id 供创建团购使用",
    rate_limit="500次/1秒",
    note="规格乘积不能超过 400。",
)

API_GOODS_INCR_QUANTITY = KttApi(
    name="pdd.ktt.goods.incr.quantity",
    label="快团团ERP增加商品库存接口",
    purpose="增减/全量设置商品库存",
    note="modify_quantity_type：不传或 1=增量修改，2=全量修改。",
)

API_GOODS_QUERY_LIST = KttApi(
    name="pdd.ktt.goods.query.list",
    label="快团团ERP商品列表查询",
    purpose="分页查询商品列表",
)

API_GOODS_QUERY_SINGLE = KttApi(
    name="pdd.ktt.goods.query.single",
    label="快团团单品查询接口",
    purpose="按 goods_id 查询单个商品详情",
)

API_GOODS_UPLOAD_IMAGE = KttApi(
    name="pdd.ktt.goods.upload.image",
    label="快团团上传商品图接口",
    purpose="按 URL 抓取并上传商品图",
    rate_limit="10次/1秒（应用级）",
    note="图片需 480~1200 像素正方形、小于 1MB；同一 URL 不可并发调用。",
)

# ---------------------------------------------------------------------------
# 订单 / 售后 / 物流
# ---------------------------------------------------------------------------

API_ORDER_LIST = KttApi(
    name="pdd.ktt.order.list", label="快团团订单列表", purpose="按成交时间拉取订单列表"
)
API_ORDER_GET = KttApi(
    name="pdd.ktt.order.get", label="快团团订单详情", purpose="按订单号查询订单信息"
)
API_ORDER_INCREMENT = KttApi(
    name="pdd.ktt.increment.order.query",
    label="快团团增量查订单",
    purpose="增量拉取订单",
)
API_ORDER_REFUND = KttApi(
    name="pdd.ktt.order.refund.get", label="快团团售后单", purpose="查询订单售后信息"
)
API_ORDER_LOGISTIC_CREATE = KttApi(
    name="pdd.ktt.order.logistic.create", label="物流发布接口", purpose="发布订单物流"
)
API_ORDER_LOGISTIC_DELETE = KttApi(
    name="pdd.ktt.order.logistic.delete", label="物流删除接口", purpose="删除订单物流"
)
API_ORDER_VOUCHER_SYNC = KttApi(
    name="pdd.ktt.order.voucher.sync", label="券码同步", purpose="同步券码"
)
API_ORDER_VOUCHER_VERIFY = KttApi(
    name="pdd.ktt.order.voucher.verify", label="券码核销", purpose="核销券码"
)
API_AFTER_SALES = KttApi(
    name="pdd.ktt.after.sales.increment.list",
    label="快团团增量售后单",
    purpose="增量拉取售后单",
)
API_HELP_SELL_COMMISSION = KttApi(
    name="pdd.ktt.help.sell.query.commission",
    label="帮卖团长查询分佣",
    purpose="查询帮卖分佣",
)
API_USER_SITE = KttApi(
    name="pdd.ktt.user.site.pagequery", label="分页查询自提点信息", purpose="查询自提点"
)

# ---------------------------------------------------------------------------
# 供货商（app 类型含「快团团」，但非团长侧核心）
# ---------------------------------------------------------------------------

API_PURCHASE_GOODS_CAT = KttApi(
    name="pdd.ktt.purchase.goods.cat.info",
    label="供货商商品库商品分类查询",
    purpose="查询供货商商品分类",
)
API_PURCHASE_GOODS_CREATE = KttApi(
    name="pdd.ktt.purchase.goods.create",
    label="供货商商品库商品创建",
    purpose="供货商侧创建商品",
)
API_PURCHASE_GOODS_BRAND = KttApi(
    name="pdd.ktt.purchase.goods.supplier.brand.info",
    label="供货商商品库供货商品牌查询",
    purpose="查询供货商品牌",
)
API_PURCHASE_SUPPLIER_GOODS = KttApi(
    name="pdd.ktt.purchase.supplier.goods.info",
    label="供货商商品库商品查询",
    purpose="查询供货商商品",
)
API_PURCHASE_SUPPLIER_STORAGE = KttApi(
    name="pdd.ktt.purchase.supplier.storage.update",
    label="供货商商品库商品库存编辑",
    purpose="编辑供货商商品库存",
)
API_PURCHASE_ORDER_LIST = KttApi(
    name="pdd.ktt.purchase.order.list",
    label="供货商订单增量列表",
    purpose="增量拉取供货商订单",
)
API_PURCHASE_ORDER_INFO = KttApi(
    name="pdd.ktt.purchase.order.info", label="供货商订单详情", purpose="供货商订单详情"
)
API_PURCHASE_ORDER_DELIVERY = KttApi(
    name="pdd.ktt.purchase.order.delivery", label="供货商订单发货", purpose="供货商发货"
)
API_PURCHASE_ORDER_AFTER_SALES = KttApi(
    name="pdd.ktt.purchase.order.after.sales.list",
    label="供货商查订单售后列表",
    purpose="供货商售后列表",
)
API_PURCHASE_ORDER_LOGISTIC_REPLACE = KttApi(
    name="pdd.ktt.purchase.order.logistic.replace",
    label="供货商订单发货物流单号替换",
    purpose="替换物流单号",
)
API_PURCHASE_SAMPLE_ORDER_LIST = KttApi(
    name="pdd.ktt.purchase.sample.order.list",
    label="供货商拍样品订单增量列表",
    purpose="拍样品订单列表",
)
API_PURCHASE_SAMPLE_ORDER_INFO = KttApi(
    name="pdd.ktt.purchase.sample.order.info",
    label="供货商拍样品订单详情",
    purpose="拍样品订单详情",
)
API_PURCHASE_SAMPLE_ORDER_DELIVERY = KttApi(
    name="pdd.ktt.purchase.sample.order.delivery",
    label="供货商拍样订单发货",
    purpose="拍样品发货",
)
API_PURCHASE_SAMPLE_ORDER_LOGISTIC = KttApi(
    name="pdd.ktt.purchase.sample.order.logistic.replace",
    label="供货商拍样品订单运单号修改",
    purpose="修改拍样品运单号",
)


# 全量注册表（按接口名索引）
ALL_KTT_APIS: dict[str, KttApi] = {
    a.name: a
    for a in (
        API_GROUP_CREATE,
        API_GROUP_QUERY_LIST,
        API_GROUP_QUERY_STATUS,
        API_GROUP_UPLOAD_IMAGE,
        API_GOODS_CREATE_SPEC,
        API_GOODS_INCR_QUANTITY,
        API_GOODS_QUERY_LIST,
        API_GOODS_QUERY_SINGLE,
        API_GOODS_UPLOAD_IMAGE,
        API_ORDER_LIST,
        API_ORDER_GET,
        API_ORDER_INCREMENT,
        API_ORDER_REFUND,
        API_ORDER_LOGISTIC_CREATE,
        API_ORDER_LOGISTIC_DELETE,
        API_ORDER_VOUCHER_SYNC,
        API_ORDER_VOUCHER_VERIFY,
        API_AFTER_SALES,
        API_HELP_SELL_COMMISSION,
        API_USER_SITE,
        API_PURCHASE_GOODS_CAT,
        API_PURCHASE_GOODS_CREATE,
        API_PURCHASE_GOODS_BRAND,
        API_PURCHASE_SUPPLIER_GOODS,
        API_PURCHASE_SUPPLIER_STORAGE,
        API_PURCHASE_ORDER_LIST,
        API_PURCHASE_ORDER_INFO,
        API_PURCHASE_ORDER_DELIVERY,
        API_PURCHASE_ORDER_AFTER_SALES,
        API_PURCHASE_ORDER_LOGISTIC_REPLACE,
        API_PURCHASE_SAMPLE_ORDER_LIST,
        API_PURCHASE_SAMPLE_ORDER_INFO,
        API_PURCHASE_SAMPLE_ORDER_DELIVERY,
        API_PURCHASE_SAMPLE_ORDER_LOGISTIC,
    )
}


# ---------------------------------------------------------------------------
# 团状态码（来自官方 group.query.list 返回说明）
# ---------------------------------------------------------------------------

GROUP_STATUS: dict[int, str] = {
    -10: "待发布",
    -5: "未开始",
    1: "跟团中",
    20: "已结束",
    30: "已删除",
}


def group_status_label(status: int | None) -> str:
    """把团状态码翻译成中文标签。"""
    if status is None:
        return "未知"
    return GROUP_STATUS.get(status, f"未知状态({status})")


def list_apis() -> list[dict]:
    """返回全部接口的结构化清单，供 capabilities 工具使用。"""
    return [
        {
            "name": a.name,
            "label": a.label,
            "purpose": a.purpose,
            "auth": a.auth,
            "rate_limit": a.rate_limit,
            "note": a.note,
        }
        for a in ALL_KTT_APIS.values()
    ]
