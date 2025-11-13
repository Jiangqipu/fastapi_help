"""风险因子与缓冲管理（问题域5）"""
from __future__ import annotations

from typing import Dict, Any, Optional


def build_risk_profile(
    slots: Dict[str, Any],
    commute_estimates: Optional[list] = None,
) -> Dict[str, Any]:
    """根据活动重要性、时段、天气等因素生成风险上下文"""
    risk = {
        "importance": 0.5,
        "time_of_day": "off_peak",
        "weather": "clear",
        "route_type": "unknown",
    }

    transportation_pref = (slots.get("transportation_preference") or "").lower()
    if "早" in slots.get("start_date", ""):
        risk["time_of_day"] = "morning_peak"
    if "晚" in slots.get("end_date", ""):
        risk["time_of_day"] = "evening_peak"

    if any(keyword in transportation_pref for keyword in ["高铁", "飞机"]):
        risk["route_type"] = "highway"

    return risk


def build_buffer_plan(commute_plans: list, risk_context: Dict[str, Any]) -> Dict[str, Any]:
    if not commute_plans:
        return {"min_buffer": 15, "max_buffer": 60, "suggestion": "根据任务重要性自行预留缓冲。"}
    buffers = [plan.get("buffer_minutes", 15) for plan in commute_plans]
    min_buffer = round(min(buffers), 1)
    max_buffer = round(max(buffers), 1)
    suggestion = (
        f"建议预留 {max_buffer} 分钟缓冲（受 {risk_context.get('weather', '天气')}"
        f" 与 {risk_context.get('time_of_day', '时段')} 影响）。"
    )
    return {"min_buffer": min_buffer, "max_buffer": max_buffer, "suggestion": suggestion}
