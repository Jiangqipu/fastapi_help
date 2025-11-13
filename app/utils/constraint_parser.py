"""时间约束解析工具：从用户文本中提取硬/软时间约束"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.models.state import (
    TimeConstraint,
    TimePreference,
    TimeWindowType,
)

SENTENCE_SPLIT_PATTERN = re.compile(r"[。！？!?\n]+")
RANGE_PATTERN = re.compile(
    r"(?P<start_prefix>凌晨|清晨|早上|上午|中午|下午|傍晚|晚上|夜间|夜里)?"
    r"\s*(?P<start_hour>\d{1,2})(?:(?:点|:)(?P<start_min>\d{1,2}))?(?P<start_half>半)?"
    r"\s*(?:到|至|-|~)\s*"
    r"(?P<end_prefix>凌晨|清晨|早上|上午|中午|下午|傍晚|晚上|夜间|夜里)?"
    r"\s*(?P<end_hour>\d{1,2})(?:(?:点|:)(?P<end_min>\d{1,2}))?(?P<end_half>半)?"
)

SINGLE_PATTERN = re.compile(
    r"(?P<prefix>凌晨|清晨|早上|上午|中午|下午|傍晚|晚上|夜间|夜里)?"
    r"\s*(?P<hour>\d{1,2})(?:(?:点|:)(?P<minute>\d{1,2}))?(?P<half>半)?"
)

HARD_KEYWORDS = ["必须", "务必", "一定", "最迟", "最晚", "不得", "准时", "前要", "之前要", "前必须"]
SOFT_KEYWORDS = ["尽量", "最好", "不要太", "不想太", "希望", "建议", "偏好", "prefer", "想"]
UPPER_BOUND_KEYWORDS = ["前", "之前", "最迟", "最晚", "不得晚于", "不晚于"]
LOWER_BOUND_KEYWORDS = ["后", "之后", "以后", "不早于", "至少", "起码"]

DAYPART_DEFAULTS = {
    "凌晨": "05:00",
    "清晨": "06:00",
    "早上": "08:00",
    "上午": "09:00",
    "中午": "12:00",
    "下午": "15:00",
    "傍晚": "18:00",
    "晚上": "19:30",
    "夜间": "21:30",
    "夜里": "22:00",
}


def parse_time_constraints(text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    解析文本中的硬/软时间约束

    Returns:
        (hard_constraints, soft_preferences)
    """
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(text)
        if sentence.strip()
    ]

    hard: List[TimeConstraint] = []
    soft: List[TimePreference] = []

    for sentence in sentences:
        constraint_type = _detect_constraint_type(sentence)
        if not constraint_type:
            continue

        window = _extract_time_window(sentence)
        if not window["earliest"] and not window["latest"]:
            # 没有提取到有效时间窗口，跳过
            continue

        activity = _extract_activity(sentence)
        description = sentence

        if constraint_type == "hard":
            hard.append(
                TimeConstraint(
                    constraint_id=str(uuid.uuid4()),
                    activity=activity,
                    earliest=window["earliest"],
                    latest=window["latest"],
                    window_type=window["window_type"],
                    description=description,
                    source_text=sentence,
                    metadata={"extraction_confidence": window["confidence"]},
                )
            )
        else:
            preference_type = _infer_preference_type(sentence, window, activity)
            weight = _infer_preference_weight(sentence)
            soft.append(
                TimePreference(
                    preference_id=str(uuid.uuid4()),
                    preference_type=preference_type,
                    activity=activity,
                    earliest=window["earliest"],
                    latest=window["latest"],
                    window_type=window["window_type"],
                    weight=weight,
                    description=description,
                    source_text=sentence,
                    metadata={"extraction_confidence": window["confidence"]},
                )
            )

    return (
        [constraint.to_dict() for constraint in hard],
        [preference.to_dict() for preference in soft],
    )


def merge_constraint_records(
    existing: List[Dict[str, Any]],
    additions: List[Dict[str, Any]],
    unique_field: str = "source_text",
) -> List[Dict[str, Any]]:
    """根据 source_text 进行去重合并"""
    seen = {record.get(unique_field): record for record in existing if record.get(unique_field)}
    merged = list(existing)

    for record in additions:
        key = record.get(unique_field)
        if key and key in seen:
            # 覆盖旧值，保留原ID
            existing_record = seen[key]
            existing_record.update(record)
        else:
            merged.append(record)
            if key:
                seen[key] = record

    return merged


def _detect_constraint_type(sentence: str) -> Optional[str]:
    lowered = sentence.lower()
    for kw in HARD_KEYWORDS:
        if kw in sentence:
            return "hard"
    for kw in SOFT_KEYWORDS:
        if kw in lowered or kw in sentence:
            return "soft"
    # 如果出现明显 deadline 词汇，也视为硬约束
    if any(kw in sentence for kw in UPPER_BOUND_KEYWORDS + LOWER_BOUND_KEYWORDS):
        return "hard"
    return None


def _extract_activity(sentence: str) -> str:
    match = re.search(r"(到|赶到|抵达|去|回)([^\d，。,.!?]{1,12})", sentence)
    if match:
        return match.group(2).strip()
    return ""


def _extract_time_window(sentence: str) -> Dict[str, Any]:
    # 优先匹配时间区间
    range_match = RANGE_PATTERN.search(sentence)
    if range_match:
        earliest = _build_time(
            range_match.group("start_hour"),
            range_match.group("start_min"),
            range_match.group("start_half"),
            range_match.group("start_prefix"),
        )
        latest = _build_time(
            range_match.group("end_hour"),
            range_match.group("end_min"),
            range_match.group("end_half"),
            range_match.group("end_prefix"),
        )
        window_type = TimeWindowType.FIXED if earliest == latest else TimeWindowType.FLEXIBLE
        return {
            "earliest": earliest,
            "latest": latest,
            "window_type": window_type,
            "confidence": 0.9,
        }

    # 处理单独时间点
    time_match = SINGLE_PATTERN.search(sentence)
    if time_match:
        normalized_time = _build_time(
            time_match.group("hour"),
            time_match.group("minute"),
            time_match.group("half"),
            time_match.group("prefix"),
        )
        direction = _infer_direction(sentence, time_match)
        if direction == "latest":
            window_type = TimeWindowType.DEADLINE
            return {
                "earliest": None,
                "latest": normalized_time,
                "window_type": window_type,
                "confidence": 0.8,
            }
        if direction == "earliest":
            window_type = TimeWindowType.OPEN
            return {
                "earliest": normalized_time,
                "latest": None,
                "window_type": window_type,
                "confidence": 0.8,
            }
        window_type = TimeWindowType.FIXED
        return {
            "earliest": normalized_time,
            "latest": normalized_time,
            "window_type": window_type,
            "confidence": 0.7,
        }

    # 使用时间段词推断
    for daypart, default_time in DAYPART_DEFAULTS.items():
        if daypart in sentence:
            return {
                "earliest": default_time,
                "latest": None,
                "window_type": TimeWindowType.OPEN,
                "confidence": 0.5,
            }

    return {
        "earliest": None,
        "latest": None,
        "window_type": TimeWindowType.FLEXIBLE,
        "confidence": 0.0,
    }


def _build_time(
    hour_str: Optional[str],
    minute_str: Optional[str],
    half_flag: Optional[str],
    prefix: Optional[str],
) -> Optional[str]:
    if hour_str is None:
        return None
    hour = int(hour_str)
    minute = int(minute_str) if minute_str else 0
    if half_flag:
        minute = 30

    if prefix:
        if prefix in {"下午", "傍晚", "晚上", "夜间", "夜里"} and hour < 12:
            hour += 12
        if prefix in {"中午"} and hour < 12:
            hour = 12 if hour == 0 else max(hour, 12)
        if prefix in {"凌晨", "清晨"} and hour == 12:
            hour = 0

    hour = hour % 24
    return f"{hour:02d}:{minute:02d}"


def _infer_direction(sentence: str, match: re.Match) -> Optional[str]:
    suffix_start = match.end()
    suffix = sentence[suffix_start : suffix_start + 6]
    prefix = sentence[max(0, match.start() - 6) : match.start()]
    combined = prefix + suffix

    if any(keyword in combined for keyword in UPPER_BOUND_KEYWORDS):
        return "latest"
    if any(keyword in combined for keyword in LOWER_BOUND_KEYWORDS):
        return "earliest"
    return None


def _infer_preference_type(sentence: str, window: Dict[str, Any], activity: str) -> str:
    if "便宜" in sentence or "价格" in sentence:
        return "budget"
    if "不要太早" in sentence or "不想太早" in sentence:
        return "avoid_early"
    if "不要太晚" in sentence or "太晚" in sentence:
        return "avoid_late"
    if window["window_type"] == TimeWindowType.OPEN and window["earliest"]:
        return "prefer_after"
    if window["window_type"] == TimeWindowType.DEADLINE and window["latest"]:
        return "prefer_before"
    return "general_preference"


def _infer_preference_weight(sentence: str) -> float:
    if "非常" in sentence or "特别" in sentence or "很" in sentence:
        return 0.8
    if "尽量" in sentence or "最好" in sentence:
        return 0.6
    return 0.4
