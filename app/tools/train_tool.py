"""12306火车票查询工具 - 使用LangChain Tool接口"""
import httpx
import json
from typing import Dict, Any, Optional, Tuple
from .base import BaseMCPTool
from .mcp_client import MCPClient
import logging

logger = logging.getLogger(__name__)


class TrainQueryTool(BaseMCPTool):
    """12306火车票查询工具"""
    
    name: str = "train_query"
    description: str = "查询12306火车票信息，包括车次、时间、价格等。参数：origin(出发地), destination(目的地), date(日期，格式：YYYY-MM-DD)"
    
    def __init__(
        self, 
        mcp_server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
        use_sse: bool = True,
        path_prefix: Optional[str] = None,
        **kwargs
    ):
        """
        初始化工具
        
        Args:
            mcp_server_url: MCP服务器URL（SSE格式）
            api_key: API密钥
            timeout: 超时时间（秒）
            use_sse: 是否使用SSE格式
            path_prefix: MCP路径前缀
            **kwargs: 传递给BaseTool的其他参数
        """
        super().__init__(
            mcp_server_url=mcp_server_url,
            api_key=api_key,
            timeout=timeout,
            use_sse=use_sse,
            **kwargs
        )
        # 兼容旧版本
        object.__setattr__(self, 'api_base_url', mcp_server_url or "https://kyfw.12306.cn")
        # 初始化MCP客户端（如果配置了服务器URL）
        if mcp_server_url:
            from app.config import settings
            if path_prefix is None:
                path_prefix = getattr(settings, 'mcp_train_path_prefix', '/tools')
            mcp_client = MCPClient(
                server_url=mcp_server_url,
                api_key=api_key,
                timeout=timeout,
                use_sse=use_sse,
                path_prefix=path_prefix
            )
            object.__setattr__(self, 'mcp_client', mcp_client)
    
    async def validate_params(self, origin: str = "", destination: str = "", date: str = "", **kwargs) -> Tuple[bool, Optional[str]]:
        """验证查询参数"""
        if not origin:
            return False, "出发地不能为空"
        if not destination:
            return False, "目的地不能为空"
        if not date:
            return False, "日期不能为空"
        # 简单日期格式验证
        if len(date) != 10 or date.count("-") != 2:
            return False, "日期格式错误，应为YYYY-MM-DD"
        return True, None
    
    async def _arun(self, origin: str, destination: str, date: str, **kwargs) -> str:
        """
        LangChain Tool接口：异步执行工具
        
        Returns:
            str: JSON格式的字符串结果
        """
        result = await self.execute(origin=origin, destination=destination, date=date, **kwargs)
        return json.dumps(result, ensure_ascii=False)
    
    async def _get_station_code(self, city_or_station_name: str) -> Optional[str]:
        """
        获取车站代码
        
        Args:
            city_or_station_name: 城市名或车站名
        
        Returns:
            车站代码或None
        """
        if not self.mcp_client:
            return None
        
        try:
            # 先尝试通过城市名查询
            result = await self.mcp_client.call_tool(
                tool_name="get-station-code-of-citys",
                parameters={"citys": city_or_station_name}
            )
            
            if result.get("status") == "success":
                data = result.get("data", {})
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, dict) and "station_code" in value:
                            station_code = value.get("station_code")
                            if station_code:
                                logger.debug(f"12306车站代码查询成功 | city={city_or_station_name} | code={station_code}")
                                return station_code
            
            result = await self.mcp_client.call_tool(
                tool_name="get-station-code-by-names",
                parameters={"stationNames": city_or_station_name}
            )
            
            if result.get("status") == "success":
                data = result.get("data", {})
                if isinstance(data, dict):
                    for key, value in data.items():
                        if isinstance(value, dict) and "station_code" in value:
                            station_code = value.get("station_code")
                            if station_code:
                                logger.debug(f"12306车站代码查询成功 | station={city_or_station_name} | code={station_code}")
                                return station_code
            
            logger.warning(f"12306无法获取车站代码 | name={city_or_station_name}")
            return None
        except Exception as e:
            logger.error(f"12306获取车站代码异常 | name={city_or_station_name} | error={str(e)}", exc_info=True)
            return None
    
    async def execute(self, origin: str, destination: str, date: str, **kwargs) -> Dict[str, Any]:
        """
        执行火车票查询
        
        Args:
            origin: 出发地（城市名或车站名）
            destination: 目的地（城市名或车站名）
            date: 出发日期，格式：YYYY-MM-DD
        
        Returns:
            Dict包含status和data
        """
        # 参数验证
        is_valid, error_msg = await self.validate_params(origin=origin, destination=destination, date=date)
        if not is_valid:
            return {
                "status": "error",
                "data": None,
                "error_message": error_msg
            }
        
        try:
            logger.info(
                f"12306火车票查询 | "
                f"origin={origin} | "
                f"destination={destination} | "
                f"date={date}"
            )
            
            if self.mcp_client:
                logger.debug(f"12306获取车站代码 | origin={origin}")
                from_station_code = await self._get_station_code(origin)
                if not from_station_code:
                    logger.error(f"12306无法获取出发站代码 | origin={origin}")
                    return {
                        "status": "error",
                        "data": None,
                        "error_message": f"无法获取出发地 '{origin}' 的车站代码"
                    }
                logger.debug(f"12306出发站代码 | origin={origin} | code={from_station_code}")
                
                logger.debug(f"12306获取车站代码 | destination={destination}")
                to_station_code = await self._get_station_code(destination)
                if not to_station_code:
                    logger.error(f"12306无法获取到达站代码 | destination={destination}")
                    return {
                        "status": "error",
                        "data": None,
                        "error_message": f"无法获取目的地 '{destination}' 的车站代码"
                    }
                logger.debug(f"12306到达站代码 | destination={destination} | code={to_station_code}")
                
                result = await self.mcp_client.call_tool(
                    tool_name="get-tickets",
                    parameters={
                        "fromStation": from_station_code,
                        "toStation": to_station_code,
                        "date": date,
                        "format": kwargs.get("format", "json")
                    }
                )
                
                if result.get("status") == "success":
                    logger.info(f"12306火车票查询成功 | origin={origin} | destination={destination} | date={date}")
                else:
                    logger.error(
                        f"12306火车票查询失败 | "
                        f"origin={origin} | "
                        f"destination={destination} | "
                        f"error={result.get('error_message')}"
                    )
                return result
            
            logger.warning("12306 MCP服务器未配置，返回模拟数据")
            mock_data = {
                "trains": [
                    {
                        "train_no": "G123",
                        "departure_time": "08:00",
                        "arrival_time": "12:30",
                        "duration": "4小时30分钟",
                        "price": {"二等座": 553, "一等座": 933, "商务座": 1748},
                        "available": True
                    },
                    {
                        "train_no": "G456",
                        "departure_time": "14:20",
                        "arrival_time": "18:50",
                        "duration": "4小时30分钟",
                        "price": {"二等座": 553, "一等座": 933, "商务座": 1748},
                        "available": True
                    }
                ],
                "query_info": {
                    "origin": origin,
                    "destination": destination,
                    "date": date
                }
            }
            
            return {
                "status": "success",
                "data": mock_data,
                "error_message": None
            }
            
        except Exception as e:
            logger.error(
                f"12306火车票查询异常 | "
                f"origin={origin} | "
                f"destination={destination} | "
                f"date={date} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"查询失败：{str(e)}"
            }

