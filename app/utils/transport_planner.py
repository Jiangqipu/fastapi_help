"""交通方案筛选与评分（问题域3）"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.utils.time_window import time_str_to_minutes, minutes_to_time_str

USER_TYPE_WEIGHTS = {
    "business": {"safety": 0.5, "price": 0.1, "comfort": 0.3, "transfer": 0.1},
    "economic": {"safety": 0.3, "price": 0.5, "comfort": 0.1, "transfer": 0.1},
    "balanced": {"safety": 0.4, "price": 0.2, "comfort": 0.2, "transfer": 0.2},
}


def infer_user_type(slots: Dict[str, Any]) -> str:
    accommodation_pref = (slots.get("accommodation_preference") or "").lower()
    transportation_pref = (slots.get("transportation_preference") or "").lower()
    if any(keyword in accommodation_pref for keyword in ["商务", "五星", "高端"]):
        return "business"
    if any(keyword in accommodation_pref for keyword in ["经济", "实惠", "青旅", "民宿"]):
        return "economic"
    if "自驾" in transportation_pref:
        return "balanced"
    return "balanced"


def _extract_price(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        prices = []
        for val in value.values():
            if isinstance(val, (int, float)):
                prices.append(float(val))
        if prices:
            return min(prices)
    if isinstance(value, list):
        prices = [float(item) for item in value if isinstance(item, (int, float))]
        if prices:
            return min(prices)
    return None


def extract_transport_candidates(tool_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for task_id, result in tool_results.items():
        data = result.get("data")
        tool_name = result.get("tool_name", "")
        if not data:
            continue

        if isinstance(data, dict) and "trains" in data:
            for train in data.get("trains", []):
                candidates.append(
                    {
                        "task_id": task_id,
                        "tool_name": tool_name,
                        "mode": "train",
                        "identifier": train.get("train_no") or train.get("code"),
                        "departure_time": train.get("departure_time"),
                        "arrival_time": train.get("arrival_time"),
                        "duration_text": train.get("duration"),
                        "price": _extract_price(train.get("price")),
                        "raw": train,
                    }
                )
        elif isinstance(data, dict) and "routes" in data:
            for route in data.get("routes", []):
                candidates.append(
                    {
                        "task_id": task_id,
                        "tool_name": tool_name,
                        "mode": route.get("mode") or "route",
                        "identifier": route.get("id"),
                        "departure_time": route.get("departure_time"),
                        "arrival_time": route.get("arrival_time"),
                        "duration_text": route.get("duration"),
                        "price": _extract_price(route.get("price")),
                        "transfers": route.get("transfers", 0),
                        "raw": route,
                    }
                )
    return candidates


def _compute_arrival_minutes(candidate: Dict[str, Any]) -> Optional[int]:
    arrival_time = candidate.get("arrival_time")
    if not arrival_time:
        return None
    arr = time_str_to_minutes(arrival_time)
    dep = time_str_to_minutes(candidate.get("departure_time"))
    if arr is None:
        return None
    if dep is not None and arr < dep:
        arr += 24 * 60
    return arr


def _compute_duration_minutes(candidate: Dict[str, Any]) -> Optional[float]:
    if candidate.get("departure_time") and candidate.get("arrival_time"):
        dep = time_str_to_minutes(candidate["departure_time"])
        arr = _compute_arrival_minutes(candidate)
        if dep is not None and arr is not None:
            return arr - dep
    duration_text = candidate.get("duration_text")
    if not duration_text:
        return None
    hours = 0
    minutes = 0
    if "小时" in duration_text:
        parts = duration_text.split("小时")
        hours = int(parts[0]) if parts[0].strip().isdigit() else 0
        if len(parts) > 1 and parts[1].strip().isdigit():
            minutes = int(parts[1].strip())
    elif ":" in duration_text:
        parts = duration_text.split(":")
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            hours = int(parts[0])
            minutes = int(parts[1])
    return hours * 60 + minutes if (hours or minutes) else None


def compute_safety_margin_minutes(
    candidate: Dict[str, Any],
    constraints: List[Dict[str, Any]],
    commute_estimates: List[Dict[str, Any]],
) -> Optional[float]:
    arrival = time_str_to_minutes(candidate.get("arrival_time"))
    if arrival is None:
        duration = _compute_duration_minutes(candidate)
        if duration is None:
            return None
        departure = time_str_to_minutes(candidate.get("departure_time") or "08:00")
        arrival = (departure or 0) + duration
    deadline_candidates = [
        c.get("latest_minutes") for c in constraints if c.get("latest_minutes") is not None
    ]
    if not deadline_candidates:
        return None
    deadline = min(deadline_candidates)
    commute_buffer = min(
        (plan.get("buffer_minutes", 0) for plan in commute_estimates),
        default=15.0,
    )
    margin = deadline - arrival - commute_buffer
    return margin


def evaluate_candidates(
    candidates: List[Dict[str, Any]],
    constraints: List[Dict[str, Any]],
    commute_estimates: List[Dict[str, Any]],
    slots: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    user_type = infer_user_type(slots)
    weights = USER_TYPE_WEIGHTS[user_type]

    feasible: List[Dict[str, Any]] = []
    infeasible: List[Dict[str, Any]] = []

    prices = [
        cand["price"] for cand in candidates if cand.get("price") is not None
    ]
    max_price = max(prices) if prices else None
    min_price = min(prices) if prices else None

    for cand in candidates:
        margin = compute_safety_margin_minutes(cand, constraints, commute_estimates)
        cand["safety_margin_minutes"] = margin
        if margin is not None and margin < 0:
            cand["feasible"] = False
            cand["infeasible_reason"] = "安全余量不足"
            infeasible.append(cand)
            continue

        duration = _compute_duration_minutes(cand)
        price = cand.get("price")
        transfers = cand.get("transfers", cand.get("raw", {}).get("transfers", 0)) or 0

        safety_score = min(1.0, max(0.0, (margin or 30) / 60)) if margin is not None else 0.5

        if max_price and min_price is not None and price is not None and max_price != min_price:
            price_score = 1 - ((price - min_price) / (max_price - min_price))
        else:
            price_score = 0.6 if price is not None else 0.5

        if duration is not None:
            comfort_score = max(0.0, 1 - duration / 600)
        else:
            comfort_score = 0.5

        transfer_score = max(0.0, 1 - transfers * 0.3)

        overall = (
            safety_score * weights["safety"]
            + price_score * weights["price"]
            + comfort_score * weights["comfort"]
            + transfer_score * weights["transfer"]
        )

        cand.update(
            {
                "feasible": True,
                "score_breakdown": {
                    "safety": round(safety_score, 3),
                    "price": round(price_score, 3),
                    "comfort": round(comfort_score, 3),
                    "transfer": round(transfer_score, 3),
                },
                "overall_score": round(overall, 3),
                "user_type": user_type,
            }
        )
        feasible.append(cand)

    feasible_sorted = sorted(feasible, key=lambda c: c.get("overall_score", 0), reverse=True)
    return feasible_sorted, infeasible


def build_plan_summary(
    feasible: List[Dict[str, Any]],
    infeasible: List[Dict[str, Any]],
) -> str:
    lines: List[str] = []
    if feasible:
        best = feasible[0]
        lines.append(
            f"最佳方案：{best.get('mode')} {best.get('identifier')}，"
            f"得分 {best.get('overall_score')}，预计 {best.get('arrival_time')} 到达，"
            f"安全余量 {minutes_to_time_str(best.get('safety_margin_minutes')) or '未知'}。"
        )
        if len(feasible) > 1:
            alt = feasible[1]
            lines.append(
                f"Plan B：{alt.get('mode')} {alt.get('identifier')}，得分 {alt.get('overall_score')}。"
            )
    else:
        lines.append("暂无满足约束的交通方案。")

    if infeasible:
        reason_counts = {}
        for plan in infeasible:
            reason = plan.get("infeasible_reason", "不可行")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reasons_text = ", ".join(f"{k}{v}条" for k, v in reason_counts.items())
        lines.append(f"被筛掉的方案：{reasons_text}")

    return "\n".join(lines)


def build_plan_variants(feasible: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    if not feasible:
        return variants

    best_balanced = feasible[0]
    time_sorted = sorted(
        feasible,
        key=lambda c: (_compute_arrival_minutes(c) if _compute_arrival_minutes(c) is not None else float("inf"))
    )
    best_time = time_sorted[0] if time_sorted else best_balanced

    variants.append(
        {
            "type": "time_priority",
            "title": "时间优先方案",
            "candidate": best_time,
            "explanation": "追求最早到达，适合 deadline 紧张场景。",
        }
    )
    variants.append(
        {
            "type": "balanced",
            "title": "平衡策略方案",
            "candidate": best_balanced,
            "explanation": "综合考虑安全、价格、舒适度及换乘，适合常规选择。",
        }
    )
    return variants


def summarize_plan_variants(variants: List[Dict[str, Any]]) -> str:
    if not variants:
        return "暂无多方案对比。"
    lines = ["多方案对比："]
    for variant in variants:
        cand = variant["candidate"]
        lines.append(
            f"- {variant['title']}: {cand.get('mode')} {cand.get('identifier')}，"
            f"到达 {cand.get('arrival_time') or '未知'}，得分 {cand.get('overall_score')}。"
            f"{variant['explanation']}"
        )
    return "\n".join(lines)
