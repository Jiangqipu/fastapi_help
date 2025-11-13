"""自定义异常"""
from typing import Optional


class TravelPlannerException(Exception):
    """出行规划器基础异常"""
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class SlotValidationError(TravelPlannerException):
    """槽位校验错误"""
    pass


class ToolExecutionError(TravelPlannerException):
    """工具执行错误"""
    pass


class LLMError(TravelPlannerException):
    """LLM调用错误"""
    pass


class StorageError(TravelPlannerException):
    """存储错误"""
    pass

