"""携程酒店查询工具 - 使用LangChain Tool接口"""
import httpx
import json
from typing import Dict, Any, Optional, Tuple
from .base import BaseMCPTool
from .mcp_client import MCPClient
import logging

logger = logging.getLogger(__name__)


class HotelQueryTool(BaseMCPTool):
    """携程酒店查询工具"""
    
    name: str = "hotel_query"
    description: str = "查询携程酒店信息，包括价格、位置、评分、房型等。参数：city(城市), check_in(入住日期，格式：YYYY-MM-DD), check_out(退房日期，格式：YYYY-MM-DD)"
    
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
        object.__setattr__(self, 'api_base_url', mcp_server_url)
        # 初始化MCP客户端（如果配置了服务器URL）
        if mcp_server_url:
            from app.config import settings
            if path_prefix is None:
                path_prefix = getattr(settings, 'mcp_hotel_path_prefix', '/tools')
            # 携程默认使用header传递key
            mcp_client = MCPClient(
                server_url=mcp_server_url,
                api_key=api_key,
                timeout=timeout,
                use_sse=use_sse,
                path_prefix=path_prefix,
                api_key_in_header=True  # 携程使用header传递key
            )
            object.__setattr__(self, 'mcp_client', mcp_client)
    
    async def validate_params(
        self, 
        city: str = "", 
        check_in: str = "", 
        check_out: str = "", 
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """验证查询参数"""
        if not city:
            return False, "城市不能为空"
        if not check_in:
            return False, "入住日期不能为空"
        if not check_out:
            return False, "退房日期不能为空"
        # 简单日期格式验证
        if len(check_in) != 10 or check_in.count("-") != 2:
            return False, "入住日期格式错误，应为YYYY-MM-DD"
        if len(check_out) != 10 or check_out.count("-") != 2:
            return False, "退房日期格式错误，应为YYYY-MM-DD"
        return True, None
    
    async def _arun(
        self, 
        city: str, 
        check_in: str, 
        check_out: str, 
        price_range: Optional[str] = None,
        hotel_type: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        LangChain Tool接口：异步执行工具
        
        Returns:
            str: JSON格式的字符串结果
        """
        result = await self.execute(
            city=city, 
            check_in=check_in, 
            check_out=check_out,
            price_range=price_range,
            hotel_type=hotel_type,
            **kwargs
        )
        return json.dumps(result, ensure_ascii=False)
    
    async def execute(
        self, 
        city: str, 
        check_in: str, 
        check_out: str, 
        price_range: Optional[str] = None,
        hotel_type: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行酒店查询
        
        Args:
            city: 城市名称
            check_in: 入住日期，格式：YYYY-MM-DD
            check_out: 退房日期，格式：YYYY-MM-DD
            price_range: 价格区间，如"200-500"
            hotel_type: 酒店类型，如"经济型/五星级/民宿"
        
        Returns:
            Dict包含status和data
        """
        # 参数验证
        is_valid, error_msg = await self.validate_params(
            city=city, check_in=check_in, check_out=check_out
        )
        if not is_valid:
            return {
                "status": "error",
                "data": None,
                "error_message": error_msg
            }
        
        try:
            logger.info(
                f"携程酒店查询 | "
                f"city={city} | "
                f"check_in={check_in} | "
                f"check_out={check_out} | "
                f"price_range={price_range} | "
                f"hotel_type={hotel_type}"
            )
            
            if self.mcp_client:
                parameters = {
                    "city": city,
                    "check_in": check_in.replace("-", "/"),
                    "check_out": check_out.replace("-", "/")
                }
                
                if price_range:
                    if "-" in price_range:
                        min_price, max_price = price_range.split("-", 1)
                        parameters["price_min"] = int(min_price.strip())
                        parameters["price_max"] = int(max_price.strip())
                    elif "," in price_range:
                        min_price, max_price = price_range.split(",", 1)
                        parameters["price_min"] = int(min_price.strip())
                        parameters["price_max"] = int(max_price.strip())
                else:
                    parameters["price_min"] = 0
                    parameters["price_max"] = 10000
                
                if hotel_type:
                    parameters["keyword"] = hotel_type
                
                logger.debug(f"携程MCP工具调用 | tool=ctrip_hotel_search | params={parameters}")
                
                result = await self.mcp_client.call_tool(
                    tool_name="ctrip_hotel_search",
                    parameters=parameters
                )
                
                if result.get("status") == "success":
                    logger.info(f"携程酒店查询成功 | city={city} | check_in={check_in} | check_out={check_out}")
                else:
                    logger.error(
                        f"携程酒店查询失败 | "
                        f"city={city} | "
                        f"check_in={check_in} | "
                        f"check_out={check_out} | "
                        f"error={result.get('error_message')}"
                    )
                
                return result
            
            logger.warning("携程MCP服务器未配置，返回模拟数据")
            mock_data = {
                "hotels": [
                    {
                        "name": "XX商务酒店",
                        "address": f"{city}市中心",
                        "price": 298,
                        "rating": 4.5,
                        "room_types": ["标准间", "大床房"],
                        "facilities": ["WiFi", "停车场", "早餐"],
                        "available": True
                    },
                    {
                        "name": "XX精品酒店",
                        "address": f"{city}商业区",
                        "price": 458,
                        "rating": 4.8,
                        "room_types": ["豪华间", "套房"],
                        "facilities": ["WiFi", "停车场", "早餐", "健身房"],
                        "available": True
                    }
                ],
                "query_info": {
                    "city": city,
                    "check_in": check_in,
                    "check_out": check_out,
                    "price_range": price_range,
                    "hotel_type": hotel_type
                }
            }
            
            return {
                "status": "success",
                "data": mock_data,
                "error_message": None
            }
            
        except Exception as e:
            logger.error(
                f"携程酒店查询异常 | "
                f"city={city} | "
                f"check_in={check_in} | "
                f"check_out={check_out} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"查询失败：{str(e)}"
            }

