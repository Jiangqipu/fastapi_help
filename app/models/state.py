"""Graph State数据模型定义"""
from typing import Dict, List, Optional, TypedDict, Any
from pydantic import BaseModel, Field
from enum import Enum


class SlotData(BaseModel):
    """槽位数据模型"""
    origin: str = Field(default="", description="出发地")
    destination: str = Field(default="", description="目的地")
    start_date: str = Field(default="", description="出发日期，格式：YYYY-MM-DD")
    end_date: str = Field(default="", description="返回日期，格式：YYYY-MM-DD")
    num_travelers: int = Field(default=1, description="出行人数")
    transportation_preference: str = Field(default="", description="交通偏好：高铁/飞机/自驾等")
    accommodation_preference: str = Field(default="", description="住宿偏好：经济型/五星级/民宿等")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class TimeWindowType(str, Enum):
    """时间窗口类型"""
    FIXED = "fixed"
    FLEXIBLE = "flexible"
    OPEN = "open"        # 只有下限
    DEADLINE = "deadline"  # 只有上限


class TimeConstraint(BaseModel):
    """硬性时间约束"""
    constraint_id: str = Field(description="约束唯一ID")
    activity: str = Field(default="", description="关联活动，如会议/到家")
    earliest: Optional[str] = Field(default=None, description="最早时间 ISO 格式 HH:MM")
    latest: Optional[str] = Field(default=None, description="最晚时间 ISO 格式 HH:MM")
    window_type: TimeWindowType = Field(default=TimeWindowType.FLEXIBLE, description="窗口类型")
    description: str = Field(default="", description="约束描述")
    source_text: str = Field(default="", description="原始文本")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加信息")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class TimePreference(BaseModel):
    """软性时间偏好"""
    preference_id: str = Field(description="偏好唯一ID")
    preference_type: str = Field(default="", description="偏好类别，如 'arrive_afternoon'")
    activity: str = Field(default="", description="关联活动")
    earliest: Optional[str] = Field(default=None, description="偏好最早时间")
    latest: Optional[str] = Field(default=None, description="偏好最晚时间")
    window_type: TimeWindowType = Field(default=TimeWindowType.FLEXIBLE, description="窗口类型")
    weight: float = Field(default=0.5, description="偏好权重 0-1")
    description: str = Field(default="", description="偏好描述")
    source_text: str = Field(default="", description="原始文本")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加信息")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class Subtask(BaseModel):
    """子任务模型"""
    task: str = Field(description="任务描述")
    tool_name: str = Field(description="使用的工具名称")
    status: str = Field(default="pending", description="任务状态：pending/running/success/failed")
    retry_count: int = Field(default=0, description="重试次数")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="任务参数")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class ToolResult(BaseModel):
    """工具执行结果模型"""
    task_id: str = Field(description="任务ID")
    tool_name: str = Field(description="工具名称")
    status: str = Field(description="执行状态：success/failed")
    data: Any = Field(default=None, description="返回数据")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    retry_count: int = Field(default=0, description="重试次数")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.model_dump()


class GraphState(TypedDict):
    """LangGraph状态定义"""
    user_id: str
    dialog_history: List[Dict[str, Any]]
    current_slots: Dict[str, Any]
    is_slots_complete: bool
    missing_slots: List[str]
    subtasks_list: List[Dict[str, Any]]
    tool_results: Dict[str, Any]
    final_plan_output: str
    user_input: Optional[str]
    validation_result: Optional[Dict[str, Any]]
    current_subtask_index: int
    hard_time_constraints: List[Dict[str, Any]]
    soft_time_preferences: List[Dict[str, Any]]
    normalized_time_constraints: List[Dict[str, Any]]
    constraint_violation: bool
    constraint_violation_message: Optional[str]
    constraint_summary: Optional[str]
    preference_breakdown: List[Dict[str, Any]]
    preference_score: Optional[float]
    preference_summary: Optional[str]
    location_candidates: Dict[str, Any]
    resolved_locations: Dict[str, Any]
    commute_estimates: List[Dict[str, Any]]
    commute_summary: Optional[str]
    transport_candidates: List[Dict[str, Any]]
    transport_plan_summary: Optional[str]
    transfer_segments: List[Dict[str, Any]]
    transfer_summary: Optional[str]
    risk_factors: Dict[str, Any]
    buffer_plan: Dict[str, Any]
    multi_plan_options: List[Dict[str, Any]]
    multi_plan_summary: Optional[str]
    missing_slots_by_level: Dict[str, List[str]]
    ambiguity_questions: List[str]

