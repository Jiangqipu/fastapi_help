"""API请求和响应模型"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class TravelPlanRequest(BaseModel):
    """出行规划请求"""
    user_id: str = Field(description="用户ID")
    user_input: str = Field(description="用户输入")
    dynamic_instructions: Optional[Dict[str, Any]] = Field(
        default=None,
        description="动态指令，用于在工具调用时插入额外参数"
    )


class TravelPlanResponse(BaseModel):
    """出行规划响应"""
    success: bool = Field(description="是否成功")
    message: str = Field(description="响应消息")
    plan_output: Optional[str] = Field(default=None, description="规划方案输出")
    current_slots: Optional[Dict[str, Any]] = Field(default=None, description="当前槽位信息")
    missing_slots: Optional[List[str]] = Field(default=None, description="缺失的槽位")
    error: Optional[str] = Field(default=None, description="错误信息")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(description="服务状态")
    version: str = Field(description="版本号")

