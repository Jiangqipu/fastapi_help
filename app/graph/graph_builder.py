"""LangGraph流程构建器"""
from langgraph.graph import StateGraph, END
from langchain_core.language_models import BaseChatModel
from app.models.state import GraphState
from app.storage import RedisStorage
from app.graph.nodes import (
    initial_input_node,
    intent_decompose_node,
    slot_validation_node,
    user_refinement_node,
    task_decomposition_node,
    tool_execution_node,
    result_validation_node,
    parameter_correction_node,
    task_scheduler_node,
    final_integration_node,
    end_node
)
import logging

logger = logging.getLogger(__name__)


def build_travel_planner_graph(
    llm1: BaseChatModel,
    llm2: BaseChatModel,
    storage: RedisStorage
):
    """
    构建完整的出行规划LangGraph流程
    
    Args:
        llm1: 主推理模型
        llm2: 校验模型
        storage: Redis存储管理器
    
    Returns:
        StateGraph: 构建好的图
    """
    # 创建状态图
    workflow = StateGraph(GraphState)
    
    # 定义节点包装函数（确保异步函数被正确调用）
    async def wrap_intent_decompose(state: GraphState) -> GraphState:
        return await intent_decompose_node(state, llm1, storage)
    
    async def wrap_slot_validation(state: GraphState) -> GraphState:
        return await slot_validation_node(state, llm2, storage)
    
    async def wrap_user_refinement(state: GraphState) -> GraphState:
        return await user_refinement_node(state, llm1, storage)
    
    async def wrap_task_decomposition(state: GraphState) -> GraphState:
        return await task_decomposition_node(state, llm1, storage)
    
    async def wrap_tool_execution(state: GraphState) -> GraphState:
        return await tool_execution_node(state, storage)
    
    async def wrap_result_validation(state: GraphState) -> GraphState:
        return await result_validation_node(state, llm2, storage)
    
    async def wrap_final_integration(state: GraphState) -> GraphState:
        return await final_integration_node(state, llm1, storage)
    
    async def wrap_parameter_correction(state: GraphState) -> GraphState:
        return await parameter_correction_node(state, llm1, storage)
    
    # 添加节点
    workflow.add_node("initial_input", initial_input_node)
    workflow.add_node("intent_decompose", wrap_intent_decompose)
    workflow.add_node("slot_validation", wrap_slot_validation)
    workflow.add_node("user_refinement", wrap_user_refinement)
    workflow.add_node("task_decomposition", wrap_task_decomposition)
    workflow.add_node("tool_execution", wrap_tool_execution)
    workflow.add_node("result_validation", wrap_result_validation)
    workflow.add_node("parameter_correction", wrap_parameter_correction)
    workflow.add_node("task_scheduler", task_scheduler_node)
    workflow.add_node("final_integration", wrap_final_integration)
    workflow.add_node("end", end_node)
    
    # 设置入口点
    workflow.set_entry_point("initial_input")
    
    # 定义边和条件跳转
    workflow.add_edge("initial_input", "intent_decompose")
    workflow.add_edge("intent_decompose", "slot_validation")
    
    # 槽位校验后的条件跳转
    def route_after_slot_validation(state: GraphState) -> str:
        """根据槽位校验结果路由"""
        is_complete = state.get("is_slots_complete", False)
        if is_complete:
            return "task_decomposition"
        else:
            return "user_refinement"
    
    workflow.add_conditional_edges(
        "slot_validation",
        route_after_slot_validation,
        {
            "task_decomposition": "task_decomposition",
            "user_refinement": "user_refinement"
        }
    )
    
    # 用户交互后返回初始输入（循环）
    workflow.add_edge("user_refinement", "initial_input")
    
    # 任务分解后的流程
    workflow.add_edge("task_decomposition", "tool_execution")
    workflow.add_edge("tool_execution", "result_validation")
    workflow.add_edge("result_validation", "task_scheduler")
    
    # 任务调度后的条件跳转
    def route_after_scheduler(state: GraphState) -> str:
        """根据任务调度结果路由"""
        # 检查是否需要参数修正
        if state.get("needs_parameter_correction", False):
            state["needs_parameter_correction"] = False  # 清除标志
            return "parameter_correction"
        
        current_index = state.get("current_subtask_index", 0)
        subtasks_list = state.get("subtasks_list", [])
        
        # 检查当前任务状态
        if current_index < len(subtasks_list):
            current_task = subtasks_list[current_index]
            task_status = current_task.get("status", "pending")
            retry_count = current_task.get("retry_count", 0)
            
            # 如果任务状态是pending且重试次数未超限，继续执行
            if task_status == "pending" and retry_count <= 3:
                return "tool_execution"
            # 如果任务已失败或成功，移动到下一个任务
            elif task_status in ["success", "failed"]:
                # 移动到下一个任务
                if current_index + 1 < len(subtasks_list):
                    return "tool_execution"
                else:
                    return "final_integration"
            else:
                # 其他情况，继续执行
                return "tool_execution"
        else:
            # 所有任务完成，进入最终整合
            return "final_integration"
    
    workflow.add_conditional_edges(
        "task_scheduler",
        route_after_scheduler,
        {
            "parameter_correction": "parameter_correction",
            "tool_execution": "tool_execution",
            "final_integration": "final_integration"
        }
    )
    
    # 参数修正后返回工具执行
    workflow.add_edge("parameter_correction", "tool_execution")
    
    # 最终整合后结束
    workflow.add_edge("final_integration", "end")
    workflow.add_edge("end", END)
    
    # 编译图
    app = workflow.compile()
    
    logger.info("LangGraph流程构建完成")
    
    return app

