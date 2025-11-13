"""API路由"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Annotated
from app.api.schemas import TravelPlanRequest, TravelPlanResponse, HealthResponse
from app.graph import build_travel_planner_graph
from app.models.state import GraphState
from app.storage import RedisStorage
from app.llm_factory import create_llm1, create_llm2
from app.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# 全局依赖（在实际应用中应该使用依赖注入）
_llm1 = None
_llm2 = None
_storage = None
_graph_app = None


def get_llm1():
    """获取LLM1实例（单例）"""
    global _llm1
    if _llm1 is None:
        _llm1 = create_llm1()
    return _llm1


def get_llm2():
    """获取LLM2实例（单例）"""
    global _llm2
    if _llm2 is None:
        _llm2 = create_llm2()
    return _llm2


def get_storage():
    """获取存储实例（单例）"""
    global _storage
    if _storage is None:
        _storage = RedisStorage()
    return _storage


async def ensure_storage_connected():
    """确保存储已连接（异步）"""
    storage = get_storage()
    if storage.redis_client is None:
        try:
            await storage.connect()
        except Exception as e:
            logger.warning(f"Redis连接失败：{str(e)}")
    return storage


def get_graph_app():
    """获取图应用实例（单例）"""
    global _graph_app
    if _graph_app is None:
        llm1 = get_llm1()
        llm2 = get_llm2()
        storage = get_storage()  # 同步获取存储实例
        _graph_app = build_travel_planner_graph(llm1, llm2, storage)
    return _graph_app


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse(
        status="healthy",
        version="0.1.0"
    )


@router.post("/plan", response_model=TravelPlanResponse)
async def create_travel_plan(
    request: TravelPlanRequest,
    graph_app: Annotated = Depends(get_graph_app)
):
    """
    创建出行规划
    
    Args:
        request: 规划请求
        storage: Redis存储
        graph_app: LangGraph应用
    
    Returns:
        TravelPlanResponse: 规划响应
    """
    try:
        user_id = request.user_id
        user_input = request.user_input
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id不能为空")
        if not user_input:
            raise HTTPException(status_code=400, detail="user_input不能为空")
        
        logger.info(f"收到规划请求：user_id={user_id}, input={user_input[:50]}...")
        
        # 获取存储实例（确保已连接）
        storage = await ensure_storage_connected()
        
        # 加载或创建初始状态
        state = await storage.load_state(user_id)
        if state is None:
            # 创建新状态
            state: GraphState = {
                "user_id": user_id,
                "dialog_history": [],
                "current_slots": {},
                "is_slots_complete": False,
                "missing_slots": [],
                "subtasks_list": [],
                "tool_results": {},
                "final_plan_output": "",
                "user_input": user_input,
                "validation_result": None,
                "current_subtask_index": 0,
                "hard_time_constraints": [],
                "soft_time_preferences": [],
                "normalized_time_constraints": [],
                "constraint_violation": False,
                "constraint_violation_message": None,
                "constraint_summary": None,
                "preference_breakdown": [],
                "preference_score": None,
                "preference_summary": None,
                "location_candidates": {},
                "resolved_locations": {},
                "commute_estimates": [],
                "commute_summary": None,
                "transport_candidates": [],
                "transport_plan_summary": None,
                "transfer_segments": [],
                "transfer_summary": None,
                "risk_factors": {},
                "buffer_plan": {},
                "multi_plan_options": [],
                "multi_plan_summary": None,
                "missing_slots_by_level": {},
                "ambiguity_questions": []
            }
        else:
            # 更新用户输入
            state["user_input"] = user_input
            state.setdefault("hard_time_constraints", [])
            state.setdefault("soft_time_preferences", [])
            state.setdefault("normalized_time_constraints", [])
            state.setdefault("constraint_violation", False)
            state.setdefault("constraint_violation_message", None)
            state.setdefault("constraint_summary", None)
            state.setdefault("preference_breakdown", [])
            state.setdefault("preference_score", None)
            state.setdefault("preference_summary", None)
            state.setdefault("location_candidates", {})
            state.setdefault("resolved_locations", {})
            state.setdefault("commute_estimates", [])
            state.setdefault("commute_summary", None)
            state.setdefault("transport_candidates", [])
            state.setdefault("transport_plan_summary", None)
            state.setdefault("transfer_segments", [])
            state.setdefault("transfer_summary", None)
            state.setdefault("risk_factors", {})
            state.setdefault("buffer_plan", {})
            state.setdefault("multi_plan_options", [])
            state.setdefault("multi_plan_summary", None)
            state.setdefault("missing_slots_by_level", {})
            state.setdefault("ambiguity_questions", [])
        
        # 添加动态指令（如果提供）
        if request.dynamic_instructions:
            state["dynamic_instructions"] = request.dynamic_instructions
        
        # 执行图流程
        try:
            # 使用astream_events或ainvoke执行图
            # 这里使用简单的ainvoke，实际可以使用流式输出
            # 设置递归限制，避免无限循环
            config = {"recursion_limit": 100}
            final_state = await graph_app.ainvoke(state, config=config)
            
            # 构建响应
            response = TravelPlanResponse(
                success=True,
                message="规划完成" if final_state.get("is_slots_complete") else "需要更多信息",
                plan_output=final_state.get("final_plan_output", ""),
                current_slots=final_state.get("current_slots", {}),
                missing_slots=final_state.get("missing_slots", []),
                error=None
            )
            
            logger.info(f"规划请求完成：user_id={user_id}")
            return response
            
        except Exception as e:
            logger.error(f"执行图流程失败：{str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"执行规划流程失败：{str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理规划请求失败：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器内部错误：{str(e)}")


@router.get("/state/{user_id}")
async def get_user_state(
    user_id: str
):
    """获取用户当前状态"""
    try:
        storage = await ensure_storage_connected()
        state = await storage.load_state(user_id)
        if state is None:
            raise HTTPException(status_code=404, detail="用户状态不存在")
        return {"success": True, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取用户状态失败：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取状态失败：{str(e)}")


@router.delete("/state/{user_id}")
async def clear_user_state(
    user_id: str
):
    """清除用户状态"""
    try:
        storage = await ensure_storage_connected()
        success = await storage.delete_state(user_id)
        if success:
            await storage.clear_history(user_id)
        return {"success": success, "message": "状态已清除" if success else "清除失败"}
    except Exception as e:
        logger.error(f"清除用户状态失败：{str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"清除状态失败：{str(e)}")

