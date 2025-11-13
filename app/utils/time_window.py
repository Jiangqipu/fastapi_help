"""时间窗口标准化、调度传播与偏好评估工具"""
from __future__ import annotations

import math
import re
import statistics
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.models.state import TimeWindowType


def time_str_to_minutes(time_str: Optional[str]) -> Optional[int]:
    """将 HH:MM 字符串转换为分钟数"""
    if not time_str:
        return None
    try:
        hour, minute = time_str.split(":")
        hour_int = int(hour)
        minute_int = int(minute)
        return hour_int * 60 + minute_int
    except Exception:
        return None


def minutes_to_time_str(minutes: Optional[int]) -> Optional[str]:
    """将分钟数转换为 HH:MM 字符串"""
    if minutes is None:
        return None
    minutes = max(0, minutes)
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def normalize_time_constraints(
    constraints: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    标准化并校验时间约束

    Returns:
        (normalized_constraints, violation_records)
    """
    normalized_list: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []
    default_duration = settings.default_travel_duration_minutes

    for constraint in constraints:
        normalized = constraint.copy()
        earliest_minutes = time_str_to_minutes(constraint.get("earliest"))
        latest_minutes = time_str_to_minutes(constraint.get("latest"))
        window_type = constraint.get("window_type") or TimeWindowType.FLEXIBLE.value

        normalized["earliest_minutes"] = earliest_minutes
        normalized["latest_minutes"] = latest_minutes
        normalized["window_type"] = window_type

        entry_violations: List[str] = []

        if earliest_minutes is not None and latest_minutes is not None:
            if earliest_minutes > latest_minutes:
                entry_violations.append("最早时间晚于最晚时间")

        last_departure_minutes: Optional[int] = None
        last_departure_time: Optional[str] = None

        if latest_minutes is not None:
            last_departure_minutes = latest_minutes - default_duration
            last_departure_time = (
                minutes_to_time_str(last_departure_minutes)
                if last_departure_minutes is not None
                else None
            )

            if last_departure_minutes is not None and last_departure_minutes < 0:
                entry_violations.append(
                    "默认行程耗时超过当前约束窗口，需要更早一天出发"
                )

            if (
                earliest_minutes is not None
                and last_departure_minutes is not None
                and last_departure_minutes < earliest_minutes
            ):
                entry_violations.append("最早可出发时间晚于允许的最晚出发时间")
        else:
            # 没有最晚时间，无法计算 last_departure
            last_departure_minutes = None
            last_departure_time = None

        normalized["last_departure_minutes"] = last_departure_minutes
        normalized["last_departure_time"] = last_departure_time
        normalized["is_feasible"] = len(entry_violations) == 0
        normalized_list.append(normalized)

        if entry_violations:
            violations.append(
                {
                    "constraint_id": constraint.get("constraint_id"),
                    "activity": constraint.get("activity", ""),
                    "messages": entry_violations,
                    "description": constraint.get("description", ""),
                    "last_departure_time": last_departure_time,
                }
            )

    return normalized_list, violations


def summarize_constraint_violations(
    violations: List[Dict[str, Any]]
) -> str:
    """将约束冲突整理为用户可读的提示"""
    if not violations:
        return ""
    lines: List[str] = ["检测到以下时间约束不可行："]
    for item in violations:
        activity = item.get("activity") or "相关活动"
        description = item.get("description") or ""
        sub_lines = "; ".join(item.get("messages", []))
        if item.get("last_departure_time"):
            sub_lines += f"，最晚出发时间约为 {item['last_departure_time']}"
        lines.append(f"- {activity}: {description}（{sub_lines}）")
    return "\n".join(lines)


# ----------  工具结果解析与调度传播  ----------

def parse_duration_to_minutes(value: Any) -> Optional[int]:
    """将多种格式的时长解析为分钟"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value > 360 and value > 24 * 60:
            return int(value / 60)
        return int(value)
    if isinstance(value, str):
        total = 0
        hour_match = re.search(r"(\d+(?:\.\d+)?)\s*小时", value)
        minute_match = re.search(r"(\d+(?:\.\d+)?)\s*分钟", value)
        if hour_match:
            total += math.floor(float(hour_match.group(1)) * 60)
        if minute_match:
            total += int(float(minute_match.group(1)))
        if total > 0:
            return total
        # 尝试纯数字字符串
        cleaned = re.sub(r"[^\d]", "", value)
        if cleaned.isdigit():
            num = int(cleaned)
            return int(num / 60) if num > 24 * 60 else num
    return None


def _strip_time_component(value: str) -> str:
    if not value:
        return value
    if " " in value:
        value = value.split(" ")[-1]
    return value.strip()


def _collect_time_fields(
    payload: Any,
    arrivals: List[int],
    departures: List[int],
    durations: List[int],
) -> None:
    if isinstance(payload, dict):
        for key, val in payload.items():
            key_lower = key.lower()
            if isinstance(val, str):
                time_value = time_str_to_minutes(_strip_time_component(val))
            else:
                time_value = None
            if "arrival" in key_lower and time_value is not None:
                arrivals.append(time_value)
            elif "departure" in key_lower and time_value is not None:
                departures.append(time_value)
            elif "duration" in key_lower:
                duration = parse_duration_to_minutes(val)
                if duration is not None:
                    durations.append(duration)
            elif isinstance(val, (dict, list)):
                _collect_time_fields(val, arrivals, departures, durations)
    elif isinstance(payload, list):
        for item in payload:
            _collect_time_fields(item, arrivals, departures, durations)


def extract_tool_time_stats(tool_results: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """从工具结果中提取可用的到达/出发/时长估计"""
    arrivals: List[int] = []
    departures: List[int] = []
    durations: List[int] = []

    for result in tool_results.values():
        data = result.get("data")
        if data is None:
            continue
        _collect_time_fields(data, arrivals, departures, durations)

    avg_duration = int(statistics.mean(durations)) if durations else None

    return {
        "min_arrival_minutes": min(arrivals) if arrivals else None,
        "max_departure_minutes": max(departures) if departures else None,
        "avg_duration_minutes": avg_duration,
    }


def apply_schedule_propagation(
    constraints: List[Dict[str, Any]],
    timing_stats: Dict[str, Optional[int]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    对时间约束执行前向/后向传播，计算EET/LST和slack
    """
    if not constraints:
        return constraints, []

    buffer_minutes = settings.default_activity_buffer_minutes
    default_duration = (
        timing_stats.get("avg_duration_minutes")
        or settings.default_activity_duration_minutes
    )

    sorted_items = sorted(
        enumerate(constraints),
        key=lambda item: item[1].get("earliest_minutes") if item[1].get("earliest_minutes") is not None else 0,
    )

    forward_prev_finish: Optional[int] = None
    for idx, constraint in sorted_items:
        duration = (
            constraint.get("metadata", {}).get("expected_duration_minutes")
            or default_duration
        )
        start = constraint.get("earliest_minutes")
        if start is None:
            start = forward_prev_finish + buffer_minutes if forward_prev_finish is not None else 0
        elif forward_prev_finish is not None:
            start = max(start, forward_prev_finish + buffer_minutes)
        finish = start + duration
        constraint["forward_start_minutes"] = start
        constraint["forward_finish_minutes"] = finish
        constraint["forward_start_time"] = minutes_to_time_str(start)
        constraint["forward_finish_time"] = minutes_to_time_str(finish)
        constraint["projected_duration_minutes"] = duration
        forward_prev_finish = finish

    violations: List[Dict[str, Any]] = []
    backward_next_start: Optional[int] = None
    for idx, constraint in reversed(sorted_items):
        duration = constraint.get("projected_duration_minutes") or default_duration
        latest_finish = constraint.get("latest_minutes")
        if latest_finish is None:
            if backward_next_start is not None:
                latest_finish = backward_next_start - buffer_minutes
            else:
                latest_finish = constraint.get("forward_finish_minutes")
        else:
            if backward_next_start is not None:
                latest_finish = min(latest_finish, backward_next_start - buffer_minutes)
        latest_start = (
            latest_finish - duration if latest_finish is not None else None
        )
        constraint["backward_start_minutes"] = latest_start
        constraint["backward_finish_minutes"] = latest_finish
        constraint["backward_start_time"] = minutes_to_time_str(latest_start)
        constraint["backward_finish_time"] = minutes_to_time_str(latest_finish)

        if (
            latest_start is not None
            and constraint.get("forward_start_minutes") is not None
        ):
            slack = latest_start - constraint["forward_start_minutes"]
            constraint["slack_minutes"] = slack
            constraint["slack_time"] = minutes_to_time_str(slack)
            if slack < 0:
                violations.append(
                    {
                        "constraint_id": constraint.get("constraint_id"),
                        "activity": constraint.get("activity", ""),
                        "messages": ["关键路径被压缩，当前日程无法满足该约束"],
                        "description": constraint.get("description", ""),
                    }
                )
        else:
            constraint["slack_minutes"] = None
            constraint["slack_time"] = None

        backward_next_start = latest_start

    return constraints, violations


def build_constraint_summary(constraints: List[Dict[str, Any]]) -> str:
    if not constraints:
        return "尚未收集到硬性时间约束。"
    lines = ["时间约束评估："]
    for constraint in constraints:
        activity = constraint.get("activity") or "相关活动"
        earliest = constraint.get("forward_start_time") or constraint.get("earliest")
        latest = constraint.get("backward_finish_time") or constraint.get("latest")
        slack = constraint.get("slack_minutes")
        slack_text = (
            f"{slack} 分钟" if slack is not None else "未知"
        )
        lines.append(
            f"- {activity}: 计划时段 {earliest or '未定'} - {latest or '未定'}，松弛度 {slack_text}"
        )
    return "\n".join(lines)


# ----------  软约束评分 ----------

def _match_constraint_for_preference(
    preference: Dict[str, Any],
    constraints: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    target = (preference.get("activity") or "").lower()
    if target:
        for constraint in constraints:
            activity = (constraint.get("activity") or "").lower()
            if target in activity or activity in target:
                return constraint
    return constraints[0] if constraints else None


def _calculate_preference_satisfaction(
    preference: Dict[str, Any],
    constraint: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    if constraint is None:
        return 0.5, "缺少对应活动，默认中性评分"

    pref_earliest = time_str_to_minutes(preference.get("earliest"))
    pref_latest = time_str_to_minutes(preference.get("latest"))
    actual_start = constraint.get("forward_start_minutes")

    if preference.get("preference_type") == "budget":
        return 0.5, "当前版本尚未支持价格偏好"

    if actual_start is None:
        return 0.6, "尚未生成具体行程，暂给中性偏高评分"

    if pref_earliest and actual_start < pref_earliest:
        diff = pref_earliest - actual_start
        penalty = min(1.0, diff / 120)  # 每提前2小时扣 1 分
        score = max(0.0, 1.0 - penalty)
        return score, f"实际开始早于偏好 {diff} 分钟"

    if pref_latest and actual_start > pref_latest:
        diff = actual_start - pref_latest
        penalty = min(1.0, diff / 120)
        score = max(0.0, 1.0 - penalty)
        return score, f"实际开始晚于偏好 {diff} 分钟"

    return 1.0, "满足偏好窗口"


def evaluate_soft_preferences(
    soft_preferences: List[Dict[str, Any]],
    constraints: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], Optional[float]]:
    if not soft_preferences:
        return [], None

    breakdown: List[Dict[str, Any]] = []
    weighted_total = 0.0
    weight_sum = 0.0

    for pref in soft_preferences:
        weight = min(max(pref.get("weight", 0.5), 0.05), 1.0)
        constraint = _match_constraint_for_preference(pref, constraints)
        score, reason = _calculate_preference_satisfaction(pref, constraint)
        breakdown.append(
            {
                "preference_id": pref.get("preference_id"),
                "description": pref.get("description", ""),
                "activity": pref.get("activity", ""),
                "score": round(score, 3),
                "weight": weight,
                "reason": reason,
            }
        )
        weighted_total += score * weight
        weight_sum += weight

    aggregate = round(weighted_total / weight_sum, 3) if weight_sum else None
    return breakdown, aggregate


def build_preference_summary(
    breakdown: List[Dict[str, Any]],
    aggregate_score: Optional[float],
) -> str:
    if not breakdown:
        return "暂无软约束偏好或尚未评分。"
    lines = []
    if aggregate_score is not None:
        lines.append(f"综合偏好得分：{aggregate_score:.2f}")
    for item in breakdown:
        desc = item.get("description") or "偏好"
        score = item.get("score")
        reason = item.get("reason")
        lines.append(f"- {desc}: 得分 {score}, {reason}")
    return "\n".join(lines)
