"""换乘与接驳规划（问题域4）"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

TRANSFER_TYPES = {
    "same_station": {"minutes": (5, 15), "risk": "低"},
    "cross_station": {"minutes": (30, 60), "risk": "高"},
    "cross_transport": {"minutes": (10, 30), "risk": "中"},
}


def _estimate_minutes(range_tuple: tuple[int, int]) -> int:
    return int(sum(range_tuple) / 2)


def build_transfer_segments(
    best_plan: Optional[Dict[str, Any]],
    resolved_locations: Dict[str, Any],
) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    if not best_plan:
        return segments

    origin = resolved_locations.get("origin", {}).get("text", "出发地")
    destination = resolved_locations.get("destination", {}).get("text", "目的地")
    mode = best_plan.get("mode", "transport")
    transfers = best_plan.get("raw", {}).get("transfers") or best_plan.get("transfers", 0)

    # 接驳段：默认只允许打车
    segments.append(
        {
            "segment": f"{origin} → {mode}出发点",
            "type": "cross_transport",
            "minutes": _estimate_minutes(TRANSFER_TYPES["cross_transport"]["minutes"]),
            "risk": TRANSFER_TYPES["cross_transport"]["risk"],
            "notes": "接驳方式限定为打车，包含出发段缓冲。",
        }
    )

    if transfers:
        transfer_type = "same_station" if transfers == 1 else "cross_station"
        segments.append(
            {
                "segment": f"{mode}内部换乘 ×{transfers}",
                "type": transfer_type,
                "minutes": _estimate_minutes(TRANSFER_TYPES[transfer_type]["minutes"]),
                "risk": TRANSFER_TYPES[transfer_type]["risk"],
                "notes": "建议提前确认站内指引。" if transfer_type == "same_station" else "预留更长时间跨站移动。",
            }
        )

    segments.append(
        {
            "segment": f"{mode}到达点 → {destination}",
            "type": "cross_transport",
            "minutes": _estimate_minutes(TRANSFER_TYPES["cross_transport"]["minutes"]),
            "risk": TRANSFER_TYPES["cross_transport"]["risk"],
            "notes": "仅允许打车接驳，包含到达缓冲。",
        }
    )

    return segments


def summarize_transfers(segments: List[Dict[str, Any]]) -> str:
    if not segments:
        return "暂无换乘/接驳需求。"
    lines = ["换乘与接驳规划："]
    total_minutes = 0
    for seg in segments:
        total_minutes += seg.get("minutes", 0)
        lines.append(
            f"- {seg['segment']}：{seg['minutes']} 分钟，风险{seg['risk']}（{seg['notes']}）"
        )
    lines.append(f"预计换乘/接驳总耗时：{total_minutes} 分钟。")
    return "\n".join(lines)
