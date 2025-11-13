"""LangGraph节点实现"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from langchain_core.language_models import BaseChatModel
from app.models.state import GraphState, SlotData
from app.prompts import (
    get_intent_decompose_prompt,
    get_slot_validation_prompt,
    get_result_validation_prompt,
    get_task_decomposition_prompt,
    get_final_integration_prompt,
    get_user_refinement_prompt,
    get_parameter_correction_prompt
)
from app.tools import BaseMCPTool, TrainQueryTool, MapQueryTool, HotelQueryTool
from app.storage import RedisStorage
from app.config import settings
from app.utils.time_window import (
    normalize_time_constraints,
    summarize_constraint_violations,
    extract_tool_time_stats,
    apply_schedule_propagation,
    build_constraint_summary,
    evaluate_soft_preferences,
    build_preference_summary,
)
from app.utils.commute import (
    build_commute_estimates,
    summarize_commute,
)
from app.utils.transport_planner import (
    extract_transport_candidates,
    evaluate_candidates,
    build_plan_summary,
)
from app.utils.transfer_planner import (
    build_transfer_segments,
    summarize_transfers,
)
from app.utils.risk_manager import build_risk_profile, build_buffer_plan
from app.utils.slot_helpers import classify_missing_slots, detect_relative_time_ambiguity
from app.utils.constraint_parser import (
    merge_constraint_records,
    parse_time_constraints,
)
from app.utils.location_parser import (
    extract_location_candidates,
    select_primary_location,
)

logger = logging.getLogger(__name__)

# 工具注册表（从配置初始化）
def get_tool_registry() -> Dict[str, BaseMCPTool]:
    """获取工具注册表，从配置读取参数"""
    return {
        "train_query": TrainQueryTool(
            mcp_server_url=settings.mcp_train_server_url,
            api_key=settings.mcp_train_api_key,
            timeout=settings.mcp_train_timeout,
            use_sse=settings.mcp_use_sse
        ),
        "map_query": MapQueryTool(
            mcp_server_url=settings.mcp_map_server_url,
            api_key=settings.mcp_map_api_key,
            timeout=settings.mcp_map_timeout,
            use_sse=settings.mcp_use_sse
        ),
        "hotel_query": HotelQueryTool(
            mcp_server_url=settings.mcp_hotel_server_url,
            api_key=settings.mcp_hotel_api_key,
            timeout=settings.mcp_hotel_timeout,
            use_sse=settings.mcp_use_sse
        )
    }

# 延迟初始化工具注册表
TOOL_REGISTRY: Dict[str, BaseMCPTool] = {}


def _validate_and_correct_dates(parameters: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """
    验证并修正日期参数
    
    Args:
        parameters: 工具参数
        tool_name: 工具名称
    
    Returns:
        Dict[str, Any]: 修正后的参数
    """
    today = datetime.now().date()
    corrected_params = parameters.copy()
    
    # 根据工具类型检查不同的日期字段
    if tool_name == "train_query":
        date_key = "date"
        if date_key in corrected_params:
            date_str = corrected_params[date_key]
            try:
                param_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                if param_date < today:
                    # 日期是过去的，修正为明天
                    tomorrow = today + timedelta(days=1)
                    corrected_params[date_key] = tomorrow.strftime("%Y-%m-%d")
                    logger.warning(
                        f"日期参数已修正 | "
                        f"tool={tool_name} | "
                        f"original_date={date_str} | "
                        f"corrected_date={corrected_params[date_key]}"
                    )
            except (ValueError, TypeError):
                # 日期格式错误，保持原值（让工具自己处理）
                pass
    
    elif tool_name == "hotel_query":
        for date_key in ["check_in", "check_out"]:
            if date_key in corrected_params:
                date_str = corrected_params[date_key]
                try:
                    param_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    if param_date < today:
                        # 日期是过去的，修正为明天
                        tomorrow = today + timedelta(days=1)
                        corrected_params[date_key] = tomorrow.strftime("%Y-%m-%d")
                        logger.warning(
                            f"日期参数已修正 | "
                            f"tool={tool_name} | "
                            f"key={date_key} | "
                            f"original_date={date_str} | "
                            f"corrected_date={corrected_params[date_key]}"
                        )
                except (ValueError, TypeError):
                    # 日期格式错误，保持原值（让工具自己处理）
                    pass
        
        # 确保 check_out 晚于 check_in
        if "check_in" in corrected_params and "check_out" in corrected_params:
            try:
                check_in = datetime.strptime(corrected_params["check_in"], "%Y-%m-%d").date()
                check_out = datetime.strptime(corrected_params["check_out"], "%Y-%m-%d").date()
                if check_out <= check_in:
                    # check_out 必须晚于 check_in，至少晚1天
                    corrected_params["check_out"] = (check_in + timedelta(days=1)).strftime("%Y-%m-%d")
                    logger.warning(
                        f"退房日期已修正 | "
                        f"tool={tool_name} | "
                        f"check_in={corrected_params['check_in']} | "
                        f"corrected_check_out={corrected_params['check_out']}"
                    )
            except (ValueError, TypeError):
                pass
    
    return corrected_params


def _detect_parameter_error(result_data: Any, error_message: Optional[str]) -> bool:
    """
    检测工具返回的错误是否是参数错误（如日期错误）
    
    Args:
        result_data: 工具返回的数据
        error_message: 错误信息
    
    Returns:
        bool: 是否是参数错误
    """
    if error_message:
        error_lower = error_message.lower()
        if any(keyword in error_lower for keyword in ["date", "日期", "cannot be earlier", "不能早于"]):
            return True
    
    if isinstance(result_data, str):
        result_lower = result_data.lower()
        if any(keyword in result_lower for keyword in ["date", "日期", "cannot be earlier", "不能早于", "error"]):
            return True
    
    return False


def _parse_json_response(response: str) -> Dict[str, Any]:
    """解析LLM返回的JSON响应"""
    try:
        # 尝试直接解析
        return json.loads(response)
    except json.JSONDecodeError:
        # 尝试提取JSON代码块
        import re
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        # 尝试提取第一个{...}块
        json_match = re.search(r'(\{.*\})', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        raise ValueError(f"无法解析JSON响应：{response[:200]}")


async def initial_input_node(state: GraphState) -> GraphState:
    """初始输入节点：接收用户输入，更新对话历史"""
    user_input = state.get("user_input", "")
    user_id = state.get("user_id", "")
    
    if not user_input:
        logger.warning("用户输入为空")
        return state
    
    # 更新对话历史
    dialog_history = state.get("dialog_history", [])
    dialog_history.append({
        "role": "user",
        "content": user_input,
        "timestamp": str(__import__("datetime").datetime.now())
    })
    
    state["dialog_history"] = dialog_history

    # 时间约束解析
    hard_constraints = state.get("hard_time_constraints", [])
    soft_preferences = state.get("soft_time_preferences", [])
    parsed_hard, parsed_soft = parse_time_constraints(user_input)
    if parsed_hard:
        hard_constraints = merge_constraint_records(hard_constraints, parsed_hard)
        state["hard_time_constraints"] = hard_constraints
        logger.info(f"解析到 {len(parsed_hard)} 条硬性时间约束")
    else:
        state.setdefault("hard_time_constraints", hard_constraints)
    if parsed_soft:
        soft_preferences = merge_constraint_records(soft_preferences, parsed_soft, unique_field="source_text")
        state["soft_time_preferences"] = soft_preferences
        logger.info(f"解析到 {len(parsed_soft)} 条软性时间偏好")
    else:
        state.setdefault("soft_time_preferences", soft_preferences)

    location_candidates = extract_location_candidates(user_input)
    if location_candidates:
        state_locations = state.get("location_candidates", {})
        for key, values in location_candidates.items():
            existing = state_locations.get(key, [])
            text_index = {item["text"]: item for item in existing}
            for candidate in values:
                text = candidate["text"]
                if text in text_index:
                    if candidate["confidence"] > text_index[text].get("confidence", 0):
                        text_index[text].update(candidate)
                else:
                    existing.append(candidate)
                    text_index[text] = candidate
            state_locations[key] = existing
        state["location_candidates"] = state_locations

        resolved = state.get("resolved_locations", {})
        if "origin" not in resolved:
            best_origin = select_primary_location(state_locations, "other")
            if best_origin:
                resolved["origin"] = best_origin
        if "destination" not in resolved:
            best_dest = select_primary_location(
                {"destination": state_locations.get("destination", [])},
                "origin",
            )
            if best_dest:
                resolved["destination"] = best_dest
        state["resolved_locations"] = resolved

        ambiguity_questions = state.get("ambiguity_questions", [])
        if len(location_candidates.get("destination", [])) > 1:
            dests = ", ".join(c["text"] for c in location_candidates["destination"][:4])
            question = f"检测到多个目的地候选（{dests}），请明确要前往的具体地点。"
            if question not in ambiguity_questions:
                ambiguity_questions.append(question)
        if len(location_candidates.get("origin", [])) > 1:
            origins = ", ".join(c["text"] for c in location_candidates["origin"][:4])
            question = f"检测到多个出发地候选（{origins}），请确认实际出发地。"
            if question not in ambiguity_questions:
                ambiguity_questions.append(question)
        time_questions = detect_relative_time_ambiguity(user_input)
        for question in time_questions:
            if question not in ambiguity_questions:
                ambiguity_questions.append(question)
        state["ambiguity_questions"] = ambiguity_questions
    
    logger.info(f"用户输入已接收：user_id={user_id}, input={user_input[:50]}...")
    return state


async def intent_decompose_node(
    state: GraphState,
    llm1: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """意图分解节点：使用LLM1填充或更新槽位"""
    try:
        current_slots = state.get("current_slots", {})
        dialog_history = state.get("dialog_history", [])
        user_input = state.get("user_input", "")
        
        # 生成提示词
        prompt = get_intent_decompose_prompt(current_slots, dialog_history, user_input)
        
        # 调用LLM
        logger.info("开始意图分解...")
        response = await llm1.ainvoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 解析JSON响应
        slots_update = _parse_json_response(response_text)
        
        # 更新槽位（保留已有值，只更新新值）
        updated_slots = {**current_slots, **slots_update}
        state["current_slots"] = updated_slots
        
        logger.info(f"槽位已更新：{updated_slots}")
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"意图分解失败：{str(e)}", exc_info=True)
        # 错误时保持原状态
        return state


async def slot_validation_node(
    state: GraphState,
    llm2: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """槽位校验节点：使用LLM2校验槽位的准确性和完整性"""
    try:
        current_slots = state.get("current_slots", {})
        
        # 生成提示词
        prompt = get_slot_validation_prompt(current_slots)
        
        # 调用LLM
        logger.info("开始槽位校验...")
        response = await llm2.ainvoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 解析JSON响应
        validation_result = _parse_json_response(response_text)
        
        # 更新状态
        state["is_slots_complete"] = validation_result.get("is_valid", False)
        state["missing_slots"] = validation_result.get("missing_fields", [])
        classified = classify_missing_slots(state["missing_slots"])
        state["missing_slots_by_level"] = classified
        state["validation_result"] = validation_result
        
        logger.info(f"槽位校验结果：is_complete={state['is_slots_complete']}, missing={state['missing_slots']}")
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"槽位校验失败：{str(e)}", exc_info=True)
        # 错误时标记为不完整
        state["is_slots_complete"] = False
        state["missing_slots"] = ["validation_error"]
        return state


async def time_constraint_node(
    state: GraphState,
    storage: RedisStorage
) -> GraphState:
    """时间约束标准化与可行性检查"""
    try:
        constraints = state.get("hard_time_constraints", [])
        if not constraints:
            state["normalized_time_constraints"] = []
            state["constraint_violation"] = False
            state["constraint_violation_message"] = None
            state["constraint_summary"] = "尚未收集到硬性时间约束。"
            await storage.save_state(state["user_id"], state)
            return state

        resolved_locations = state.get("resolved_locations", {})
        commute_plans = []
        risk_context = state.get("risk_factors", {})
        if not risk_context:
            risk_context = build_risk_profile(state.get("current_slots", {}), state.get("commute_estimates"))
            state["risk_factors"] = risk_context
        if resolved_locations:
            commute_plans = build_commute_estimates(
                resolved_locations,
                importance=state.get("preference_score") or 0.5,
                risk_context=risk_context,
            )
            state["commute_estimates"] = commute_plans
            state["commute_summary"] = summarize_commute(commute_plans)
            state["buffer_plan"] = build_buffer_plan(commute_plans, risk_context)
        else:
            state.setdefault("commute_estimates", [])
            state.setdefault("commute_summary", "尚未生成通勤估算。")
            state.setdefault("buffer_plan", {})

        tool_results = state.get("tool_results", {})
        timing_stats = extract_tool_time_stats(tool_results)
        if not timing_stats.get("avg_duration_minutes") and commute_plans:
            avg_commute = sum(plan["total_minutes"] for plan in commute_plans) / len(commute_plans)
            timing_stats["avg_duration_minutes"] = avg_commute

        normalized, violations = normalize_time_constraints(constraints)
        normalized, propagation_violations = apply_schedule_propagation(
            normalized, timing_stats
        )
        violations.extend(propagation_violations)
        state["normalized_time_constraints"] = normalized
        state["constraint_summary"] = build_constraint_summary(normalized)

        if violations:
            message = summarize_constraint_violations(violations)
            state["constraint_violation"] = True
            state["constraint_violation_message"] = message
            state["final_plan_output"] = message
            state["validation_result"] = {
                "is_valid": False,
                "reason": message
            }
            logger.warning(f"时间约束不可行：{message}")
        else:
            state["constraint_violation"] = False
            state["constraint_violation_message"] = None
            if not state.get("constraint_summary"):
                state["constraint_summary"] = "所有硬性时间约束均可行。"

        await storage.save_state(state["user_id"], state)
        return state

    except Exception as e:
        logger.error(f"时间约束检查失败：{str(e)}", exc_info=True)
        return state


async def preference_scoring_node(
    state: GraphState,
    storage: RedisStorage
) -> GraphState:
    """软约束评分节点"""
    try:
        if state.get("constraint_violation"):
            state["preference_breakdown"] = []
            state["preference_score"] = None
            state["preference_summary"] = None
            await storage.save_state(state["user_id"], state)
            return state

        preferences = state.get("soft_time_preferences", [])
        constraints = state.get("normalized_time_constraints", [])
        breakdown, aggregate = evaluate_soft_preferences(preferences, constraints)
        state["preference_breakdown"] = breakdown
        state["preference_score"] = aggregate
        state["preference_summary"] = build_preference_summary(breakdown, aggregate)
        await storage.save_state(state["user_id"], state)
        return state
    except Exception as e:
        logger.error(f"软约束评分失败：{str(e)}", exc_info=True)
        return state


async def transport_planning_node(
    state: GraphState,
    storage: RedisStorage
) -> GraphState:
    """交通方案筛选与评分"""
    try:
        if state.get("constraint_violation"):
            state["transport_candidates"] = []
            state["transport_plan_summary"] = "由于硬性时间约束不可行，交通方案被跳过。"
            await storage.save_state(state["user_id"], state)
            return state

        tool_results = state.get("tool_results", {})
        candidates = extract_transport_candidates(tool_results)
        normalized_constraints = state.get("normalized_time_constraints", [])
        commute_estimates = state.get("commute_estimates", [])
        slots = state.get("current_slots", {})

        if not candidates:
            state["transport_candidates"] = []
            state["transport_plan_summary"] = "工具结果中没有识别出可评估的交通方案。"
            await storage.save_state(state["user_id"], state)
            return state

        feasible, infeasible = evaluate_candidates(
            candidates, normalized_constraints, commute_estimates, slots
        )

        plan_summary = build_plan_summary(feasible, infeasible)
        best_plan = feasible[0] if feasible else None
        transfer_segments = build_transfer_segments(best_plan, state.get("resolved_locations", {}))
        transfer_summary = summarize_transfers(transfer_segments)
        plan_variants = build_plan_variants(feasible)
        multi_plan_summary = summarize_plan_variants(plan_variants)

        state["transport_candidates"] = feasible
        state["transport_plan_summary"] = plan_summary
        state["transfer_segments"] = transfer_segments
        state["transfer_summary"] = transfer_summary
        state["multi_plan_options"] = plan_variants
        state["multi_plan_summary"] = multi_plan_summary
        await storage.save_state(state["user_id"], state)
        return state

    except Exception as e:
        logger.error(f"交通方案评估失败：{str(e)}", exc_info=True)
        return state


async def user_refinement_node(
    state: GraphState,
    llm1: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """用户交互提示节点：生成友好提示，等待用户补充信息"""
    try:
        missing_levels = state.get("missing_slots_by_level", {"L1": [], "L3": [], "others": []})
        ambiguity_questions = state.get("ambiguity_questions", [])
        
        # 生成提示词
        prompt = get_user_refinement_prompt(
            missing_levels.get("L1", []),
            missing_levels.get("L3", []),
            missing_levels.get("others", []),
            ambiguity_questions
        )
        
        # 调用LLM生成友好提示
        logger.info("生成用户交互提示...")
        response = await llm1.ainvoke(prompt)
        refinement_message = response.content if hasattr(response, 'content') else str(response)
        
        # 添加到对话历史
        dialog_history = state.get("dialog_history", [])
        dialog_history.append({
            "role": "assistant",
            "content": refinement_message,
            "timestamp": str(__import__("datetime").datetime.now())
        })
        state["dialog_history"] = dialog_history
        
        # 更新最终输出（临时提示）
        state["final_plan_output"] = refinement_message
        
        logger.info(f"用户交互提示已生成：{refinement_message[:50]}...")
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"生成用户交互提示失败：{str(e)}", exc_info=True)
        # 生成默认提示
        missing_text = "、".join(missing_slots)
        default_message = f"请提供以下信息：{missing_text}"
        state["final_plan_output"] = default_message
        return state


async def task_decomposition_node(
    state: GraphState,
    llm1: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """任务分解节点：根据完整槽位生成子任务列表"""
    try:
        current_slots = state.get("current_slots", {})
        
        # 生成提示词
        prompt = get_task_decomposition_prompt(current_slots)
        
        # 调用LLM
        logger.info("开始任务分解...")
        response = await llm1.ainvoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 解析JSON响应
        decomposition_result = _parse_json_response(response_text)
        subtasks = decomposition_result.get("subtasks", [])
        
        # 初始化子任务状态
        subtasks_list = []
        for i, subtask in enumerate(subtasks):
            subtasks_list.append({
                "task": subtask.get("task", ""),
                "tool_name": subtask.get("tool_name", ""),
                "status": "pending",
                "retry_count": 0,
                "parameters": subtask.get("parameters", {}),
                "task_id": f"task_{i}"
            })
        
        state["subtasks_list"] = subtasks_list
        state["current_subtask_index"] = 0
        state["tool_results"] = {}
        
        logger.info(f"任务已分解，共{len(subtasks_list)}个子任务")
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"任务分解失败：{str(e)}", exc_info=True)
        state["subtasks_list"] = []
        return state


async def tool_execution_node(
    state: GraphState,
    storage: RedisStorage
) -> GraphState:
    """工具执行节点：并行调用MCP工具"""
    try:
        subtasks_list = state.get("subtasks_list", [])
        current_index = state.get("current_subtask_index", 0)
        tool_results = state.get("tool_results", {})
        
        if current_index >= len(subtasks_list):
            logger.warning("所有任务已完成")
            return state
        
        # 获取当前任务
        current_task = subtasks_list[current_index]
        task_id = current_task.get("task_id", f"task_{current_index}")
        tool_name = current_task.get("tool_name", "")
        parameters = current_task.get("parameters", {})
        
        # 更新任务状态
        current_task["status"] = "running"
        subtasks_list[current_index] = current_task
        
        logger.info(f"执行任务：{task_id}, 工具：{tool_name}, 参数：{parameters}")
        
        # 获取工具实例（延迟初始化）
        if not TOOL_REGISTRY:
            TOOL_REGISTRY.update(get_tool_registry())
        tool = TOOL_REGISTRY.get(tool_name)
        if not tool:
            error_msg = f"工具 {tool_name} 未注册"
            logger.error(error_msg)
            tool_results[task_id] = {
                "task_id": task_id,
                "tool_name": tool_name,
                "status": "error",
                "data": None,
                "error_message": error_msg,
                "retry_count": current_task.get("retry_count", 0)
            }
            current_task["status"] = "failed"
            subtasks_list[current_index] = current_task
            state["subtasks_list"] = subtasks_list
            state["tool_results"] = tool_results
            return state
        
        # 执行工具前验证日期参数
        parameters = _validate_and_correct_dates(parameters, tool_name)
        
        # 执行工具（支持动态指令插入）
        # 这里可以从state中获取动态指令并合并到parameters中
        dynamic_instructions = state.get("dynamic_instructions", {})
        if tool_name in dynamic_instructions:
            parameters = {**parameters, **dynamic_instructions[tool_name]}
        
        # 调用工具
        result = await tool.execute(**parameters)
        
        # 记录工具返回数据（完整记录）
        result_status = result.get("status", "error")
        result_data = result.get("data")
        error_message = result.get("error_message")
        
        # 将返回数据序列化为JSON字符串用于日志（完整记录）
        try:
            if result_data:
                data_json = json.dumps(result_data, ensure_ascii=False, indent=2)
                logger.info(
                    f"工具执行返回数据 | "
                    f"task_id={task_id} | "
                    f"tool={tool_name} | "
                    f"status={result_status} | "
                    f"data_size={len(data_json)} | "
                    f"data={data_json}"
                )
            else:
                logger.warning(
                    f"工具执行返回数据为空 | "
                    f"task_id={task_id} | "
                    f"tool={tool_name} | "
                    f"status={result_status} | "
                    f"error={error_message}"
                )
        except Exception as e:
            logger.warning(
                f"工具返回数据序列化失败 | "
                f"task_id={task_id} | "
                f"tool={tool_name} | "
                f"error={str(e)}"
            )
            # 如果序列化失败，记录数据类型和字符串表示
            if result_data:
                logger.info(
                    f"工具执行返回数据 | "
                    f"task_id={task_id} | "
                    f"tool={tool_name} | "
                    f"status={result_status} | "
                    f"data_type={type(result_data).__name__} | "
                    f"data_repr={str(result_data)}"
                )
        
        # 保存结果
        tool_results[task_id] = {
            "task_id": task_id,
            "tool_name": tool_name,
            "status": result_status,
            "data": result_data,
            "error_message": error_message,
            "retry_count": current_task.get("retry_count", 0)
        }
        
        # 更新任务状态
        if result_status == "success":
            current_task["status"] = "success"
        else:
            current_task["status"] = "failed"
        
        subtasks_list[current_index] = current_task
        
        state["subtasks_list"] = subtasks_list
        state["tool_results"] = tool_results
        
        logger.info(
            f"任务执行完成 | "
            f"task_id={task_id} | "
            f"tool={tool_name} | "
            f"status={current_task['status']}"
        )
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"工具执行失败：{str(e)}", exc_info=True)
        # 标记当前任务失败
        current_index = state.get("current_subtask_index", 0)
        subtasks_list = state.get("subtasks_list", [])
        if current_index < len(subtasks_list):
            current_task = subtasks_list[current_index]
            current_task["status"] = "failed"
            subtasks_list[current_index] = current_task
            state["subtasks_list"] = subtasks_list
        return state


async def result_validation_node(
    state: GraphState,
    llm2: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """结果校验节点：使用LLM2校验工具返回结果"""
    try:
        subtasks_list = state.get("subtasks_list", [])
        current_index = state.get("current_subtask_index", 0)
        tool_results = state.get("tool_results", {})
        
        if current_index >= len(subtasks_list):
            return state
        
        current_task = subtasks_list[current_index]
        task_id = current_task.get("task_id", f"task_{current_index}")
        task_description = current_task.get("task", "")
        
        # 获取工具结果
        result = tool_results.get(task_id, {})
        tool_raw_output = result.get("data")
        
        # 记录校验前的工具结果数据（完整记录）
        try:
            if tool_raw_output:
                output_json = json.dumps(tool_raw_output, ensure_ascii=False, indent=2)
                logger.debug(
                    f"结果校验前数据 | "
                    f"task_id={task_id} | "
                    f"data_size={len(output_json)} | "
                    f"data={output_json}"
                )
        except Exception:
            pass  # 如果序列化失败，跳过记录
        
        # 生成提示词
        prompt = get_result_validation_prompt(task_description, tool_raw_output)
        
        # 调用LLM
        logger.info(f"校验任务结果 | task_id={task_id}")
        response = await llm2.ainvoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 解析JSON响应
        validation_result = _parse_json_response(response_text)
        is_acceptable = validation_result.get("is_acceptable", False)
        
        # 记录校验结果
        logger.info(
            f"结果校验完成 | "
            f"task_id={task_id} | "
            f"is_acceptable={is_acceptable} | "
            f"validation={json.dumps(validation_result, ensure_ascii=False)}"
        )
        
        # 更新结果中的校验信息
        result["validation"] = validation_result
        tool_results[task_id] = result
        
        # 更新状态
        state["tool_results"] = tool_results
        state["validation_result"] = validation_result
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"结果校验失败：{str(e)}", exc_info=True)
        # 校验失败时标记为不可接受
        validation_result = {"is_acceptable": False, "reason": f"校验过程出错：{str(e)}"}
        state["validation_result"] = validation_result
        return state


async def parameter_correction_node(
    state: GraphState,
    llm1: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """参数修正节点：根据错误信息修正工具参数"""
    try:
        subtasks_list = state.get("subtasks_list", [])
        current_index = state.get("current_subtask_index", 0)
        tool_results = state.get("tool_results", {})
        
        if current_index >= len(subtasks_list):
            return state
        
        current_task = subtasks_list[current_index]
        task_id = current_task.get("task_id", f"task_{current_index}")
        task_description = current_task.get("task", "")
        original_parameters = current_task.get("parameters", {})
        
        # 获取工具结果和错误信息
        result = tool_results.get(task_id, {})
        result_data = result.get("data")
        error_message = result.get("error_message")
        
        # 检测是否是参数错误
        if not _detect_parameter_error(result_data, error_message):
            # 不是参数错误，不需要修正
            return state
        
        # 生成错误信息文本
        error_text = error_message or str(result_data) if result_data else "未知错误"
        
        # 生成提示词
        prompt = get_parameter_correction_prompt(task_description, original_parameters, error_text)
        
        # 调用LLM修正参数
        logger.info(f"开始修正参数 | task_id={task_id} | error={error_text[:100]}")
        response = await llm1.ainvoke(prompt)
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 解析JSON响应
        correction_result = _parse_json_response(response_text)
        corrected_parameters = correction_result.get("corrected_parameters", {})
        correction_reason = correction_result.get("correction_reason", "")
        
        if corrected_parameters:
            # 更新任务参数
            updated_parameters = {**original_parameters, **corrected_parameters}
            current_task["parameters"] = updated_parameters
            subtasks_list[current_index] = current_task
            state["subtasks_list"] = subtasks_list
            
            logger.info(
                f"参数修正完成 | "
                f"task_id={task_id} | "
                f"reason={correction_reason} | "
                f"original={original_parameters} | "
                f"corrected={updated_parameters}"
            )
            
            # 保存状态
            await storage.save_state(state["user_id"], state)
        else:
            logger.warning(f"参数修正失败，未获得有效修正 | task_id={task_id}")
        
        return state
        
    except Exception as e:
        logger.error(f"参数修正失败：{str(e)}", exc_info=True)
        return state


async def task_scheduler_node(state: GraphState) -> GraphState:
    """任务调度节点：根据校验结果决定下一步"""
    validation_result = state.get("validation_result", {})
    is_acceptable = validation_result.get("is_acceptable", False)
    
    subtasks_list = state.get("subtasks_list", [])
    current_index = state.get("current_subtask_index", 0)
    
    # 检查是否所有任务都已完成
    if current_index >= len(subtasks_list):
        # 所有任务完成，进入最终整合
        logger.info("所有任务已完成，进入最终整合")
        return state
    
    current_task = subtasks_list[current_index]
    retry_count = current_task.get("retry_count", 0)
    max_retry = 3
    
    if is_acceptable:
        # 校验通过，标记为成功，进入下一个任务
        current_task["status"] = "success"
        subtasks_list[current_index] = current_task
        state["subtasks_list"] = subtasks_list
        state["current_subtask_index"] = current_index + 1
        
        # 如果还有任务，继续执行；否则进入最终整合
        if current_index + 1 < len(subtasks_list):
            logger.info(f"任务{current_index}成功，继续执行下一个任务")
        else:
            logger.info("所有任务执行成功，进入最终整合")
    else:
        # 校验不通过
        # 检查是否是参数错误，如果是，先尝试参数修正
        result = tool_results.get(current_task.get("task_id", f"task_{current_index}"), {})
        result_data = result.get("data")
        error_message = result.get("error_message")
        
        is_parameter_error = _detect_parameter_error(result_data, error_message)
        
        if is_parameter_error and retry_count == 0:
            # 第一次失败且是参数错误，标记需要参数修正
            state["needs_parameter_correction"] = True
            logger.info(f"任务{current_index}检测到参数错误，需要修正参数")
        elif retry_count < max_retry:
            # 重试
            current_task["retry_count"] = retry_count + 1
            current_task["status"] = "pending"  # 重置为pending以便重试
            subtasks_list[current_index] = current_task
            state["subtasks_list"] = subtasks_list
            # 不更新current_subtask_index，保持当前索引以便重试
            logger.info(f"任务{current_index}校验失败，准备重试（{retry_count + 1}/{max_retry}）")
        else:
            # 超过重试次数，标记为失败，移动到下一个任务
            current_task["status"] = "failed"
            subtasks_list[current_index] = current_task
            state["subtasks_list"] = subtasks_list
            state["current_subtask_index"] = current_index + 1
            logger.warning(f"任务{current_index}超过最大重试次数，标记为失败，继续下一个任务")
            
            # 如果这是最后一个任务，直接进入最终整合
            if current_index + 1 >= len(subtasks_list):
                logger.info("所有任务已完成（部分失败），进入最终整合")
    
    return state


async def final_integration_node(
    state: GraphState,
    llm1: BaseChatModel,
    storage: RedisStorage
) -> GraphState:
    """最终整合节点：汇总所有结果，生成最终规划方案"""
    try:
        current_slots = state.get("current_slots", {})
        tool_results = state.get("tool_results", {})
        
        constraint_summary = state.get("constraint_summary")
        preference_summary = state.get("preference_summary")
        commute_summary = state.get("commute_summary")
        transport_summary = state.get("transport_plan_summary")
        transfer_summary = state.get("transfer_summary")
        buffer_plan = state.get("buffer_plan")
        multi_plan_summary = state.get("multi_plan_summary")
        # 生成提示词
        prompt = get_final_integration_prompt(
            current_slots,
            tool_results,
            constraint_summary,
            preference_summary,
            commute_summary,
            transport_summary,
            transfer_summary,
            buffer_plan,
            multi_plan_summary
        )
        
        # 调用LLM
        logger.info("开始最终结果整合...")
        response = await llm1.ainvoke(prompt)
        final_output = response.content if hasattr(response, 'content') else str(response)
        
        # 更新最终输出
        state["final_plan_output"] = final_output
        
        # 添加到对话历史
        dialog_history = state.get("dialog_history", [])
        dialog_history.append({
            "role": "assistant",
            "content": final_output,
            "timestamp": str(__import__("datetime").datetime.now())
        })
        state["dialog_history"] = dialog_history
        
        logger.info("最终规划方案已生成")
        
        # 保存状态
        await storage.save_state(state["user_id"], state)
        
        return state
        
    except Exception as e:
        logger.error(f"最终整合失败：{str(e)}", exc_info=True)
        error_message = f"生成规划方案时出错：{str(e)}"
        state["final_plan_output"] = error_message
        return state


async def end_node(state: GraphState) -> GraphState:
    """结束节点"""
    logger.info(f"流程结束：user_id={state.get('user_id')}")
    return state

