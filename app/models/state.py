"""Graph State数据模型定义"""
from typing import Dict, List, Optional, TypedDict, Any
from pydantic import BaseModel, Field


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

