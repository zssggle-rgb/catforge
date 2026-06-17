"""Rule-based entity extraction for M06 comment signals."""

from __future__ import annotations

from app.services.core3_real_data.comment_downstream_signal_schemas import CommentEntityExtraction


ENTITY_TERMS: dict[str, tuple[str, ...]] = {
    "scenarios": (
        "客厅",
        "卧室",
        "白天",
        "晚上",
        "装修",
        "新家",
        "看球",
        "电影",
        "追剧",
        "游戏",
        "大屏",
        "85",
    ),
    "actions": (
        "看球",
        "追剧",
        "看电影",
        "打游戏",
        "玩主机",
        "投屏",
        "语音",
        "安装",
        "配送",
        "换新",
        "挂墙",
    ),
    "people": (
        "家人",
        "全家",
        "父母",
        "老人",
        "长辈",
        "孩子",
        "儿童",
        "宝宝",
        "画质党",
    ),
    "objects": (
        "PS5",
        "ps5",
        "Switch",
        "switch",
        "主机",
        "球赛",
        "体育",
        "电影",
        "机顶盒",
    ),
    "experience_results": (
        "清晰",
        "清楚",
        "色彩好",
        "细腻",
        "流畅",
        "不卡",
        "不拖影",
        "震撼",
        "方便",
        "简单",
        "护眼",
        "不累",
        "音质好",
        "亮度够",
        "暗场好",
        "划算",
        "值得",
    ),
    "constraints": (
        "价格",
        "预算",
        "空间",
        "光线",
        "操作复杂",
        "广告",
        "售后",
    ),
    "price_terms": (
        "性价比",
        "划算",
        "值得",
        "买得值",
        "优惠",
        "活动",
        "补贴",
        "赠品",
        "太贵",
        "不值",
        "降价",
        "背刺",
        "保价",
        "这个价",
    ),
    "service_terms": (
        "安装",
        "师傅",
        "配送",
        "物流",
        "客服",
        "售后",
        "送货",
        "挂装",
        "包装",
    ),
    "negative_terms": (
        "模糊",
        "偏色",
        "不清楚",
        "反光",
        "画质差",
        "拖影",
        "卡顿",
        "延迟",
        "掉帧",
        "广告",
        "弹窗",
        "系统卡",
        "复杂",
        "破音",
        "声音小",
        "音质差",
        "刺眼",
        "累眼",
        "故障",
        "坏点",
        "品控差",
        "做工差",
        "太贵",
        "不值",
        "降价",
        "背刺",
        "配送慢",
        "安装差",
        "客服差",
        "售后差",
    ),
}


class CommentEntityExtractor:
    def extract(self, sentence_text: str, *, extra_keywords: list[str] | None = None) -> CommentEntityExtraction:
        matched = {
            field_name: _match_terms(sentence_text, terms)
            for field_name, terms in ENTITY_TERMS.items()
        }
        matched_keywords = _dedupe([term for terms in matched.values() for term in terms])
        if extra_keywords:
            matched_keywords.extend(term for term in _match_terms(sentence_text, extra_keywords) if term not in matched_keywords)
        return CommentEntityExtraction(
            scenarios=matched["scenarios"],
            actions=matched["actions"],
            people=matched["people"],
            objects=matched["objects"],
            experience_results=matched["experience_results"],
            constraints=matched["constraints"],
            price_terms=matched["price_terms"],
            service_terms=matched["service_terms"],
            negative_terms=matched["negative_terms"],
            matched_keywords=matched_keywords,
        )


def _match_terms(text: str, terms: tuple[str, ...] | list[str]) -> list[str]:
    lower_text = text.lower()
    result: list[str] = []
    for term in terms:
        if term and term.lower() in lower_text and term not in result:
            result.append(term)
    return result


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
