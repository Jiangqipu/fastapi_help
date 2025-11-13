"""地理实体解析工具：实现 L1-L3 地址解析与歧义处理"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

CITY_SUFFIXES = ("市", "州", "盟")
REGION_KEYWORDS = ("区", "县", "镇", "乡", "开发区", "新区")
LANDMARK_KEYWORDS = (
    "大厦",
    "中心",
    "酒店",
    "广场",
    "学院",
    "大学",
    "公司",
    "机场",
    "车站",
    "地铁站",
    "火车站",
    "汽车站",
    "写字楼",
    "产业园",
    "公园",
    "景区",
)
ADDRESS_DETAILS = ("路", "街", "巷", "弄", "号", "-", "室", "栋")

ORIGIN_PATTERNS = [
    re.compile(r"从(?P<loc>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,20})(?:出发|出门|启程)"),
    re.compile(r"起点[为是](?P<loc>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,20})"),
]

DEST_PATTERNS = [
    re.compile(r"(?:到|去|前往|抵达)(?P<loc>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,20})(?:参加|开会|办理|入住|集合)?"),
    re.compile(r"目的地[为是](?P<loc>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,20})"),
]

GENERIC_PATTERNS = [
    re.compile(r"在(?P<loc>[\u4e00-\u9fa5A-Za-z0-9·\-\s]{1,20})(?:附近|周边|这里)?"),
]


def classify_location_level(text: str) -> Tuple[str, float]:
    """依据文本特征估算地址层级"""
    if any(keyword in text for keyword in ADDRESS_DETAILS):
        return "L3", 0.9
    if any(keyword in text for keyword in LANDMARK_KEYWORDS) or any(
        keyword in text for keyword in REGION_KEYWORDS
    ):
        return "L2", 0.75
    if text.endswith(CITY_SUFFIXES) or len(text) <= 4:
        return "L1", 0.6
    return "L2", 0.5


def build_candidate(
    text: str,
    role: str,
    context: Optional[str] = None,
    source: str = "",
) -> Dict[str, Any]:
    """封装候选地址"""
    level, confidence = classify_location_level(text)
    return {
        "text": text.strip(),
        "level": level,
        "confidence": confidence,
        "role": role,
        "context": context or "",
        "source": source,
    }


def extract_location_candidates(user_text: str) -> Dict[str, List[Dict[str, Any]]]:
    """返回 origin/destination/other 的候选地址"""
    result: Dict[str, List[Dict[str, Any]]] = {
        "origin": [],
        "destination": [],
        "other": [],
    }

    for pattern in ORIGIN_PATTERNS:
        for match in pattern.finditer(user_text):
            loc = match.group("loc").strip()
            if not loc:
                continue
            result["origin"].append(build_candidate(loc, "origin", source="pattern"))

    for pattern in DEST_PATTERNS:
        for match in pattern.finditer(user_text):
            loc = match.group("loc").strip()
            if not loc:
                continue
            context = user_text[max(0, match.start() - 8) : match.start()]
            result["destination"].append(
                build_candidate(loc, "destination", context=context, source="pattern")
            )

    if not result["origin"] and not result["destination"]:
        for pattern in GENERIC_PATTERNS:
            for match in pattern.finditer(user_text):
                loc = match.group("loc").strip()
                if loc:
                    result["other"].append(
                        build_candidate(loc, "other", source="generic")
                    )

    # 去重
    for key in result:
        unique: Dict[str, Dict[str, Any]] = {}
        for candidate in result[key]:
            text = candidate["text"]
            if text not in unique or candidate["confidence"] > unique[text]["confidence"]:
                unique[text] = candidate
        result[key] = list(unique.values())

    return result


def select_primary_location(
    candidates: Dict[str, List[Dict[str, Any]]],
    fallback_key: str,
) -> Optional[Dict[str, Any]]:
    """挑选主要地点：优先级 L3 > L2 > L1 > 其他"""
    priority = {"L3": 3, "L2": 2, "L1": 1}

    def best_from_list(items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not items:
            return None
        return max(
            items,
            key=lambda item: (priority.get(item.get("level", ""), 0), item.get("confidence", 0)),
        )

    for key in ("origin", "destination", fallback_key, "other"):
        best = best_from_list(candidates.get(key, []))
        if best:
            return best
    return None
