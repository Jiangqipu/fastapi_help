"""MCP工具基类 - 兼容LangChain Tool接口"""
from abc import abstractmethod
from typing import Dict, Any, Optional, Tuple
from langchain_core.tools import BaseTool
from pydantic import Field, ConfigDict
import logging

logger = logging.getLogger(__name__)


class BaseMCPTool(BaseTool):
    """MCP工具基类，继承LangChain的BaseTool"""
    
    # 使用Pydantic v2的model_config
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # MCP工具通用字段（定义为Pydantic字段）
    mcp_server_url: Optional[str] = Field(default=None, exclude=True)
    api_key: Optional[str] = Field(default=None, exclude=True)
    timeout: int = Field(default=30, exclude=True)
    use_sse: bool = Field(default=True, exclude=True)
    mcp_client: Optional[Any] = Field(default=None, exclude=True)
    api_base_url: Optional[str] = Field(default=None, exclude=True)
    
    def __init__(self, **kwargs):
        """初始化工具"""
        # 从类属性获取name和description
        class_name = getattr(self.__class__, 'name', None)
        class_desc = getattr(self.__class__, 'description', None)
        
        # 设置默认值
        if 'name' not in kwargs and class_name:
            kwargs['name'] = class_name
        if 'description' not in kwargs and class_desc:
            kwargs['description'] = class_desc
        
        # 提取MCP相关参数
        mcp_params = {
            'mcp_server_url': kwargs.pop('mcp_server_url', None),
            'api_key': kwargs.pop('api_key', None),
            'timeout': kwargs.pop('timeout', 30),
            'use_sse': kwargs.pop('use_sse', True),
        }
        
        super().__init__(**kwargs)
        
        # 使用object.__setattr__来设置字段，绕过Pydantic验证
        object.__setattr__(self, 'mcp_server_url', mcp_params['mcp_server_url'])
        object.__setattr__(self, 'api_key', mcp_params['api_key'])
        object.__setattr__(self, 'timeout', mcp_params['timeout'])
        object.__setattr__(self, 'use_sse', mcp_params['use_sse'])
        object.__setattr__(self, 'mcp_client', None)
        object.__setattr__(self, 'api_base_url', mcp_params['mcp_server_url'])
    
    @abstractmethod
    async def _arun(self, **kwargs) -> str:
        """
        LangChain Tool接口：异步执行工具
        
        Returns:
            str: JSON格式的字符串结果
        """
        raise NotImplementedError(f"工具 {self.name} 必须实现 _arun 方法")
    
    def _run(self, **kwargs) -> str:
        """
        LangChain Tool接口：同步执行工具（MCP工具通常是异步的）
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self._arun(**kwargs))
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行工具查询并返回结果（兼容旧接口）
        
        Returns:
            Dict[str, Any]: 包含status和data的字典
        """
        result_str = await self._arun(**kwargs)
        try:
            import json
            return json.loads(result_str)
        except json.JSONDecodeError:
            return {
                "status": "success",
                "data": result_str,
                "error_message": None
            }
    
    async def validate_params(self, **kwargs) -> Tuple[bool, Optional[str]]:
        """
        验证参数
        
        Returns:
            tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        return True, None

