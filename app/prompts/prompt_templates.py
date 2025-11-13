"""LLM提示词模板"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime


def get_intent_decompose_prompt(
    current_slots: Dict[str, Any],
    dialog_history: List[Dict[str, Any]],
    user_input: str
) -> str:
    """
    生成意图分解与槽位填充的提示词
    
    Args:
        current_slots: 当前槽位数据
        dialog_history: 对话历史
        user_input: 用户输入
    
    Returns:
        str: 完整的提示词
    """
    # 获取当前日期作为参考
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 格式化对话历史
    history_text = ""
    for msg in dialog_history[-10:]:  # 只取最近10条
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        history_text += f"{role}: {content}\n"
    
    prompt = f"""你是一个专业的出行规划助手。根据用户最新的输入和完整的对话历史，请识别并提取旅行规划所需的关键信息（出发地、目的地、日期、人数、偏好等）。

**重要提示：**
- 今天是 {today}
- 日期必须是今天或未来的日期，不能是过去的日期
- 如果用户说"下周三"、"明天"等相对日期，请根据今天计算准确的日期

**当前已填充的槽位：**
{_format_slots(current_slots)}

**对话历史：**
{history_text if history_text else "（暂无历史对话）"}

**用户最新输入：**
{user_input}

**任务要求：**
1. 仔细分析用户输入和对话历史，提取或更新槽位信息
2. 如果信息缺失，请在对应键上输出空字符串 ""
3. 日期格式必须为 YYYY-MM-DD，且必须是今天或未来的日期
4. 人数必须是正整数
5. 只输出一个完整的 JSON 对象，不要包含任何其他文字

**输出格式（JSON）：**
{{
    "origin": "出发地城市名称",
    "destination": "目的地城市名称",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "num_travelers": 1,
    "transportation_preference": "高铁/飞机/自驾/无偏好",
    "accommodation_preference": "经济型/五星级/民宿/无偏好"
}}

请直接输出JSON对象，不要包含markdown代码块标记："""
    
    return prompt


def get_slot_validation_prompt(current_slots: Dict[str, Any]) -> str:
    """
    生成槽位校验的提示词
    
    Args:
        current_slots: 当前槽位数据
    
    Returns:
        str: 完整的提示词
    """
    # 获取当前日期作为参考
    today = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""你的任务是严格校验以下提供的槽位数据是否完整且合理。旅行规划的核心槽位（出发地、目的地、开始日期）必须完整。

**重要提示：**
- 今天是 {today}
- 日期必须是今天或未来的日期，不能是过去的日期

**当前槽位数据：**
{_format_slots(current_slots)}

**校验规则：**
1. 核心槽位（origin、destination、start_date）必须非空
2. 日期格式必须为 YYYY-MM-DD
3. 日期必须合理（必须是今天或未来的日期，不能是过去的日期）
4. end_date 如果存在，必须晚于 start_date
5. num_travelers 必须是正整数
6. 城市名称必须合理（不能是空字符串或明显错误）

**输出格式（JSON）：**
如果校验通过：
{{
    "is_valid": true,
    "missing_fields": [],
    "reason": "所有核心槽位已填充且合理。"
}}

如果校验不通过：
{{
    "is_valid": false,
    "missing_fields": ["字段名1", "字段名2"],
    "reason": "详细的校验失败原因"
}}

请直接输出JSON对象，不要包含markdown代码块标记："""
    
    return prompt


def get_result_validation_prompt(
    subtask_description: str,
    tool_raw_output: Any
) -> str:
    """
    生成工具结果校验的提示词
    
    Args:
        subtask_description: 子任务描述
        tool_raw_output: 工具返回的原始数据
    
    Returns:
        str: 完整的提示词
    """
    # 格式化工具输出
    output_text = str(tool_raw_output)
    if isinstance(tool_raw_output, dict):
        import json
        output_text = json.dumps(tool_raw_output, ensure_ascii=False, indent=2)
    
    prompt = f"""请判断以下工具返回的原始数据是否有效，是否包含规划所需的关键信息。

**子任务描述：**
{subtask_description}

**工具返回的原始数据：**
{output_text}

**校验标准：**
1. 查询结果不能为空（至少包含一条有效数据）
2. 数据不能明显异常（例如，价格为0或负数、日期错误、距离为0等）
3. 必须包含完成任务所需的关键字段
4. 如果status为"error"，则校验不通过

**输出格式（JSON）：**
如果结果有效：
{{
    "is_acceptable": true,
    "reason": "结果有效，包含X条可选信息。"
}}

如果结果无效：
{{
    "is_acceptable": false,
    "reason": "详细的失败原因，例如：查询结果为空，没有找到任何车票。"
}}

请直接输出JSON对象，不要包含markdown代码块标记："""
    
    return prompt


def get_task_decomposition_prompt(current_slots: Dict[str, Any]) -> str:
    """
    生成任务分解的提示词
    
    Args:
        current_slots: 完整的槽位数据
    
    Returns:
        str: 完整的提示词
    """
    prompt = f"""根据用户完整的出行需求，将任务分解为多个可执行的子任务。

**用户需求（槽位信息）：**
{_format_slots(current_slots)}

**可用工具：**
1. train_query - 查询12306火车票信息
2. map_query - 查询高德地图路线规划、POI信息
3. hotel_query - 查询携程酒店信息

**任务分解要求：**
1. 根据用户需求，确定需要调用哪些工具
2. 为每个工具调用生成一个子任务
3. 每个子任务需要包含：task（任务描述）、tool_name（工具名称）、parameters（工具参数）
4. 任务应该按照逻辑顺序排列（例如：先查交通，再查住宿）

**输出格式（JSON）：**
{{
    "subtasks": [
        {{
            "task": "查询从北京到上海的火车票",
            "tool_name": "train_query",
            "parameters": {{
                "origin": "北京",
                "destination": "上海",
                "date": "2024-01-15"
            }}
        }},
        {{
            "task": "查询上海的酒店信息",
            "tool_name": "hotel_query",
            "parameters": {{
                "city": "上海",
                "check_in": "2024-01-15",
                "check_out": "2024-01-17"
            }}
        }}
    ]
}}

请直接输出JSON对象，不要包含markdown代码块标记："""
    
    return prompt


def get_final_integration_prompt(
    current_slots: Dict[str, Any],
    tool_results: Dict[str, Any],
    constraint_summary: Optional[str] = None,
    preference_summary: Optional[str] = None,
    commute_summary: Optional[str] = None,
    transport_summary: Optional[str] = None,
    transfer_summary: Optional[str] = None,
    buffer_plan: Optional[Dict[str, Any]] = None,
    multi_plan_summary: Optional[str] = None,
) -> str:
    """
    生成最终结果整合的提示词
    
    Args:
        current_slots: 槽位数据
        tool_results: 所有工具执行结果
    
    Returns:
        str: 完整的提示词
    """
    # 格式化工具结果
    results_text = ""
    for task_id, result in tool_results.items():
        status = result.get("status", "unknown")
        data = result.get("data")
        error = result.get("error_message")
        results_text += f"\n任务ID: {task_id}\n"
        results_text += f"状态: {status}\n"
        if status == "success" and data:
            import json
            results_text += f"数据: {json.dumps(data, ensure_ascii=False, indent=2)}\n"
        elif error:
            results_text += f"错误: {error}\n"
        results_text += "-" * 50 + "\n"
    
    prompt = f"""你是一个专业的出行规划助手。请根据用户需求和所有工具查询结果，生成一份完整、专业、结构化的出行规划方案。

**用户需求：**
{_format_slots(current_slots)}

**工具查询结果：**
{results_text}

**时间可行性分析：**
{constraint_summary or "暂无约束数据"}

**软约束偏好评分：**
{preference_summary or "暂无偏好信息"}

**通勤估算：**
{commute_summary or "尚未生成通勤估算"}

**交通方案评分：**
{transport_summary or "暂无交通方案评估"}

**换乘与接驳计划：**
{transfer_summary or "暂无换乘信息"}

**缓冲建议：**
{_format_buffer_plan(buffer_plan)}

**多方案对比：**
{multi_plan_summary or "暂无多方案对比。"}

**输出要求：**
1. 生成一份完整的出行规划方案，包括：
   - 行程概览
   - 交通方案（车次、时间、价格等）
   - 住宿推荐（酒店、价格、位置等）
   - 其他建议（如路线规划、注意事项等）
2. 如果某些查询失败，请在方案中说明原因，并给出替代建议
3. 使用清晰的结构和友好的语言
4. 突出关键信息（时间、价格、地点等）

**输出格式：**
直接输出规划方案文本，不需要JSON格式。"""
    
    return prompt


def get_parameter_correction_prompt(
    task_description: str,
    original_parameters: Dict[str, Any],
    error_message: str
) -> str:
    """
    生成参数修正的提示词
    
    Args:
        task_description: 任务描述
        original_parameters: 原始参数
        error_message: 错误信息
    
    Returns:
        str: 完整的提示词
    """
    # 获取当前日期作为参考
    today = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""工具调用失败，需要根据错误信息修正参数。

**重要提示：**
- 今天是 {today}
- 日期必须是今天或未来的日期，不能是过去的日期

**任务描述：**
{task_description}

**原始参数：**
{json.dumps(original_parameters, ensure_ascii=False, indent=2)}

**错误信息：**
{error_message}

**任务要求：**
1. 仔细分析错误信息，找出参数中的问题
2. 如果是日期错误（例如"日期不能早于今天"），请将日期修正为今天或未来的日期
3. 如果是其他参数错误，请根据错误信息进行相应修正
4. 只修正有问题的参数，保留其他正确的参数
5. 如果无法确定如何修正，请保持原参数不变

**输出格式（JSON）：**
{{
    "corrected_parameters": {{
        "参数名1": "修正后的值1",
        "参数名2": "修正后的值2"
    }},
    "correction_reason": "修正原因说明"
}}

请直接输出JSON对象，不要包含markdown代码块标记："""
    
    return prompt


def get_user_refinement_prompt(
    critical_slots: List[str],
    optional_slots: List[str],
    other_slots: List[str],
    ambiguity_questions: List[str]
) -> str:
    """
    生成用户交互提示的提示词
    """
    critical_text = "、".join(critical_slots) if critical_slots else "（无）"
    optional_text = "、".join(optional_slots) if optional_slots else "（无）"
    other_text = "、".join(other_slots) if other_slots else "（无）"
    ambiguity_text = "\n".join(f"- {item}" for item in ambiguity_questions) if ambiguity_questions else "（无歧义问题）"
    
    prompt = f"""请根据以下分级信息，为用户生成一个友好、清晰的提示，引导其补充必要信息和澄清歧义。优先询问 L1 关键槽位，然后再询问可选槽位；若存在歧义问题，也请单独提出澄清。

**L1 必填槽位：**
{critical_text}

**可选槽位：**
{optional_text}

**其他槽位：**
{other_text}

**歧义问题：**
{ambiguity_text}

**要求：**
1. 使用友好、自然的语言，逐条说明需要用户提供的信息。
2. 先处理 L1，再处理可选槽位，最后提及歧义澄清。
3. 对歧义问题给出示例，例如“请确认会议在北京哪个区或地标附近？”。
4. 保持简洁，不要过于冗长。

**输出格式：**
直接输出中文提示文本，不需要JSON格式。"""
    
    return prompt


def _format_slots(slots: Dict[str, Any]) -> str:
    """格式化槽位数据为可读文本"""
    lines = []
    for key, value in slots.items():
        if value:  # 只显示非空值
            lines.append(f"  - {key}: {value}")
    if not lines:
        return "  （暂无槽位信息）"
    return "\n".join(lines)


def _format_buffer_plan(plan: Optional[Dict[str, Any]]) -> str:
    if not plan:
        return "暂无缓冲建议。"
    min_buffer = plan.get("min_buffer")
    max_buffer = plan.get("max_buffer")
    suggestion = plan.get("suggestion", "")
    parts = []
    if min_buffer is not None and max_buffer is not None:
        parts.append(f"推荐缓冲区间：{min_buffer}-{max_buffer} 分钟。")
    if suggestion:
        parts.append(suggestion)
    return " ".join(parts) if parts else "暂无缓冲建议。"

