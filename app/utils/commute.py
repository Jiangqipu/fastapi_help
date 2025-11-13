"""通勤时间估算公式 MVP"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.utils.time_window import minutes_to_time_str

MODE_CONFIG = {
    "walk": {"speed_kmh": 4, "departure": 3, "arrival": 3, "wait": 0, "risk": 1.0},
    "bike": {"speed_kmh": 12, "departure": 4, "arrival": 4, "wait": 0, "risk": 1.1},
    "metro": {"speed_kmh": 30, "departure": 8, "arrival": 8, "wait": 5, "risk": 1.2},
    "bus": {"speed_kmh": 18, "departure": 6, "arrival": 6, "wait": 8, "risk": 1.4},
    "taxi": {"speed_kmh": 25, "departure": 5, "arrival": 5, "wait": 4, "risk": 1.3},
    "drive": {"speed_kmh": 28, "departure": 5, "arrival": 5, "wait": 0, "risk": 1.25},
    "train": {"speed_kmh": 200, "departure": 15, "arrival": 20, "wait": 15, "risk": 1.1},
    "flight": {"speed_kmh": 750, "departure": 30, "arrival": 30, "wait": 25, "risk": 1.5},
}

TIME_OF_DAY_FACTORS = {
    "morning_peak": 1.3,
    "evening_peak": 1.4,
    "off_peak": 1.0,
    "late_night": 1.2,
}

WEATHER_FACTORS = {
    "clear": 1.0,
    "rain": 1.2,
    "storm": 1.5,
    "snow": 1.4,
}

ROUTE_RISK_FACTORS = {
    "highway": 1.0,
    "urban": 1.2,
    "unknown": 1.1,
}


def infer_distance_km(origin: Optional[Dict[str, Any]], destination: Optional[Dict[str, Any]]) -> float:
    """根据文本层级粗略估计距离"""
    if not origin or not destination:
        return 10.0
    origin_city = origin.get("text", "")[:2]
    destination_city = destination.get("text", "")[:2]
    origin_level = origin.get("level", "L2")
    destination_level = destination.get("level", "L2")

    if origin_city and destination_city and origin_city != destination_city:
        return 1200.0
    if origin_level == destination_level == "L3":
        return 5.0
    if origin_level == destination_level == "L2":
        return 12.0
    return 80.0


def recommend_modes(distance_km: float) -> List[str]:
    if distance_km < 1:
        return ["walk", "bike"]
    if distance_km < 3:
        return ["bike", "taxi", "drive"]
    if distance_km < 10:
        return ["metro", "taxi", "drive"]
    if distance_km < 50:
        return ["metro", "drive", "taxi"]
    if distance_km < 300:
        return ["train", "drive"]
    return ["train", "flight"]


def compute_commute_time(
    distance_km: float,
    mode: str,
    importance: float = 0.5,
    risk_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = MODE_CONFIG.get(mode, MODE_CONFIG["taxi"])
    risk_context = risk_context or {}
    speed = cfg["speed_kmh"]
    base_travel = (distance_km / speed) * 60

    time_of_day_factor = TIME_OF_DAY_FACTORS.get(risk_context.get("time_of_day", "off_peak"), 1.0)
    weather_factor = WEATHER_FACTORS.get(risk_context.get("weather", "clear"), 1.0)
    route_factor = ROUTE_RISK_FACTORS.get(risk_context.get("route_type", "unknown"), 1.0)

    core_time = base_travel * cfg["risk"] * time_of_day_factor * weather_factor * route_factor
    total = (
        cfg["departure"]
        + cfg["wait"]
        + core_time
        + cfg["arrival"]
    )
    buffer_ratio = max(0.1, min(0.5, 0.1 + importance * 0.4))
    buffer_ratio *= max(time_of_day_factor, weather_factor, route_factor)
    buffer = total * buffer_ratio
    total_with_buffer = total + buffer

    return {
        "mode": mode,
        "distance_km": round(distance_km, 1),
        "departure_cost": cfg["departure"],
        "wait_time": cfg["wait"],
        "core_travel_minutes": round(core_time, 1),
        "arrival_cost": cfg["arrival"],
        "buffer_minutes": round(buffer, 1),
        "total_minutes": round(total_with_buffer, 1),
        "time_of_day_factor": time_of_day_factor,
        "weather_factor": weather_factor,
        "route_factor": route_factor,
        "risk_context": risk_context,
    }


def build_commute_estimates(
    resolved_locations: Dict[str, Any],
    importance: float = 0.5,
    preferred_modes: Optional[List[str]] = None,
    risk_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    origin = resolved_locations.get("origin")
    destination = resolved_locations.get("destination")
    distance_km = infer_distance_km(origin, destination)

    modes = preferred_modes or recommend_modes(distance_km)
    plans = [
        compute_commute_time(distance_km, mode, importance, risk_context)
        for mode in modes
    ]
    return plans


def summarize_commute(plans: List[Dict[str, Any]]) -> str:
    if not plans:
        return "尚未生成通勤估算。"
    best = min(plans, key=lambda p: p["total_minutes"])
    return (
        f"推荐方式：{best['mode']}，预计耗时 {best['total_minutes']} 分钟 "
        f"(距离约 {best['distance_km']}km，含缓冲 {best['buffer_minutes']} 分钟)。"
    )
