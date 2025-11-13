"""槽位缺失分级与歧义检测辅助"""
from __future__ import annotations

import re
from typing import Dict, List

CRITICAL_SLOTS = {"origin", "destination", "start_date"}
OPTIONAL_SLOTS = {"end_date", "num_travelers", "transportation_preference", "accommodation_preference"}

RELATIVE_TIME_PATTERNS = [
    re.compile(pattern) for pattern in [
        r"下周[一二三四五六日天]?",
        r"明天",
        r"后天",
        r"下个月",
        r"本周末",
    ]
]


def classify_missing_slots(missing_slots: List[str]) -> Dict[str, List[str]]:
    result = {"L1": [], "L3": [], "others": []}
    for slot in missing_slots:
        if slot in CRITICAL_SLOTS:
            result["L1"].append(slot)
        elif slot in OPTIONAL_SLOTS:
            result["L3"].append(slot)
        else:
            result["others"].append(slot)
    return result


def detect_relative_time_ambiguity(user_input: str) -> List[str]:
    questions: List[str] = []
    for pattern in RELATIVE_TIME_PATTERNS:
        if pattern.search(user_input):
            questions.append("请确认具体的日期（例如提供 YYYY-MM-DD）。")
            break
    return questions
