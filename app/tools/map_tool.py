"""高德地图查询工具 - 使用LangChain Tool接口"""
import httpx
import json
from typing import Dict, Any, Optional, Tuple
from .base import BaseMCPTool
from .mcp_client import MCPClient
import logging

logger = logging.getLogger(__name__)


class MapQueryTool(BaseMCPTool):
    """高德地图查询工具（路线规划、POI查询等）"""
    
    name: str = "map_query"
    description: str = "查询高德地图路线规划、POI信息、距离和时间估算。参数：origin(起点), destination(终点), query_type(查询类型：route/poi/distance)"
    
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
            api_key: 高德地图API Key
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
        object.__setattr__(self, 'api_base_url', mcp_server_url or "https://restapi.amap.com")
        # 初始化MCP客户端（如果配置了服务器URL）
        if mcp_server_url:
            from app.config import settings
            # 使用配置的路径前缀，如果没有则使用默认值
            if path_prefix is None:
                path_prefix = getattr(settings, 'mcp_map_path_prefix', '/tools')
            mcp_client = MCPClient(
                server_url=mcp_server_url,
                api_key=api_key,
                timeout=timeout,
                use_sse=use_sse,
                path_prefix=path_prefix
            )
            object.__setattr__(self, 'mcp_client', mcp_client)
            logger.info(
                f"高德地图MCP工具初始化成功 | "
                f"server_url={mcp_server_url} | "
                f"path_prefix={path_prefix} | "
                f"use_sse={use_sse}"
            )
        else:
            logger.warning("高德地图MCP服务器URL未配置，将使用模拟数据")
    
    async def validate_params(self, origin: str = "", destination: str = "", query_type: str = "route", **kwargs) -> Tuple[bool, Optional[str]]:
        """验证查询参数"""
        if not origin:
            return False, "起点不能为空"
        if not destination:
            return False, "终点不能为空"
        if query_type not in ["route", "poi", "distance"]:
            return False, f"查询类型错误，应为route/poi/distance之一，当前：{query_type}"
        return True, None
    
    async def _arun(self, origin: str, destination: str, query_type: str = "route", **kwargs) -> str:
        """
        LangChain Tool接口：异步执行工具
        
        Returns:
            str: JSON格式的字符串结果
        """
        result = await self.execute(origin=origin, destination=destination, query_type=query_type, **kwargs)
        return json.dumps(result, ensure_ascii=False)
    
    async def _geocode_address(self, address: str, city: Optional[str] = None) -> Optional[str]:
        """
        将地址转换为经纬度坐标（格式：经度,纬度）
        
        Args:
            address: 地址字符串
            city: 城市名称（可选）
        
        Returns:
            经纬度字符串（格式：经度,纬度）或None
        """
        if not self.mcp_client:
            return None
        
        try:
            # 调用地理编码工具
            params = {"address": address}
            if city:
                params["city"] = city
            
            result = await self.mcp_client.call_tool(
                tool_name="maps_geo",
                parameters=params
            )
            
            if result.get("status") == "success":
                data = result.get("data", {})
                geocodes = None
                
                if isinstance(data, dict) and "geocodes" in data:
                    geocodes = data.get("geocodes", [])
                elif isinstance(data, dict) and "results" in data:
                    results = data.get("results", [])
                    if results and len(results) > 0:
                        first_result = results[0]
                        if isinstance(first_result, dict):
                            if "location" in first_result:
                                location = first_result.get("location", "")
                                if location:
                                    logger.debug(f"高德地理编码成功 | address={address} | location={location}")
                                    return location
                            if "geocodes" in first_result:
                                geocodes = first_result.get("geocodes", [])
                elif isinstance(data, list) and len(data) > 0:
                    for item in data:
                        if isinstance(item, dict) and "geocodes" in item:
                            geocodes = item.get("geocodes", [])
                            break
                
                if geocodes and len(geocodes) > 0:
                    first_geocode = geocodes[0]
                    if isinstance(first_geocode, dict):
                        location = first_geocode.get("location", "")
                        if location:
                            logger.debug(f"高德地理编码成功 | address={address} | location={location}")
                            return location
                
                logger.warning(f"高德无法提取地理编码location | address={address} | data_type={type(data).__name__}")
            else:
                logger.warning(f"高德地理编码失败 | address={address} | error={result.get('error_message')}")
            return None
        except Exception as e:
            logger.error(f"高德地理编码异常 | address={address} | error={str(e)}", exc_info=True)
            return None
    
    async def execute(self, origin: str, destination: str, query_type: str = "route", **kwargs) -> Dict[str, Any]:
        """
        执行地图查询
        
        Args:
            origin: 起点（可以是地址或经纬度，格式：经度,纬度）
            destination: 终点（可以是地址或经纬度，格式：经度,纬度）
            query_type: 查询类型（route路线规划/poi地点查询/distance距离计算）
        
        Returns:
            Dict包含status和data
        """
        # 参数验证
        is_valid, error_msg = await self.validate_params(
            origin=origin, destination=destination, query_type=query_type
        )
        if not is_valid:
            return {
                "status": "error",
                "data": None,
                "error_message": error_msg
            }
        
        try:
            logger.info(
                f"高德地图查询 | "
                f"origin={origin} | "
                f"destination={destination} | "
                f"type={query_type}"
            )
            
            if self.mcp_client:
                def is_coordinate(coord_str: str) -> bool:
                    """检查字符串是否是经纬度格式（经度,纬度）"""
                    if "," not in coord_str:
                        return False
                    parts = coord_str.split(",")
                    if len(parts) != 2:
                        return False
                    try:
                        float(parts[0].strip())
                        float(parts[1].strip())
                        return True
                    except ValueError:
                        return False
                
                origin_coord = origin
                if not is_coordinate(origin):
                    logger.debug(f"高德地理编码 | address={origin}")
                    origin_coord = await self._geocode_address(origin)
                    if not origin_coord:
                        logger.error(f"高德无法转换起点坐标 | origin={origin}")
                        return {
                            "status": "error",
                            "data": None,
                            "error_message": f"无法将起点 '{origin}' 转换为经纬度坐标"
                        }
                    logger.debug(f"高德起点坐标 | origin={origin} | coord={origin_coord}")
                
                dest_coord = destination
                if not is_coordinate(destination):
                    logger.debug(f"高德地理编码 | address={destination}")
                    dest_coord = await self._geocode_address(destination)
                    if not dest_coord:
                        logger.error(f"高德无法转换终点坐标 | destination={destination}")
                        return {
                            "status": "error",
                            "data": None,
                            "error_message": f"无法将终点 '{destination}' 转换为经纬度坐标"
                        }
                    logger.debug(f"高德终点坐标 | destination={destination} | coord={dest_coord}")
                
                tool_mapping = {
                    "route": "maps_direction_driving",
                    "poi": "maps_text_search",
                    "distance": "maps_distance"
                }
                amap_tool_name = tool_mapping.get(query_type, "maps_direction_driving")
                
                if query_type == "route":
                    parameters = {"origin": origin_coord, "destination": dest_coord}
                elif query_type == "poi":
                    parameters = {"keywords": destination, "city": kwargs.get("city", "")}
                elif query_type == "distance":
                    parameters = {
                        "origins": origin_coord,
                        "destination": dest_coord,
                        "type": kwargs.get("type", "1")
                    }
                else:
                    parameters = {"origin": origin_coord, "destination": dest_coord}
                
                logger.debug(f"高德MCP工具调用 | tool={amap_tool_name} | params={parameters}")
                
                result = await self.mcp_client.call_tool(
                    tool_name=amap_tool_name,
                    parameters=parameters
                )
                
                if result.get("status") == "success":
                    logger.info(f"高德地图查询成功 | type={query_type} | origin={origin} | destination={destination}")
                else:
                    logger.error(
                        f"高德地图查询失败 | "
                        f"type={query_type} | "
                        f"origin={origin} | "
                        f"destination={destination} | "
                        f"error={result.get('error_message')}"
                    )
                
                return result
            
            logger.warning("高德MCP服务器未配置，返回模拟数据")
            mock_data = {
                "query_type": query_type,
                "origin": origin,
                "destination": destination,
                "route_info": {
                    "distance": "350公里",
                    "duration": "4小时20分钟",
                    "toll_distance": "320公里",
                    "tolls": "约150元",
                    "paths": [
                        {
                            "distance": 350,
                            "duration": 260,
                            "strategy": "最快路线"
                        }
                    ]
                } if query_type == "route" else None,
                "poi_info": {
                    "name": destination,
                    "address": f"{destination}详细地址",
                    "location": {"lng": 116.397428, "lat": 39.90923}
                } if query_type == "poi" else None
            }
            
            return {
                "status": "success",
                "data": mock_data,
                "error_message": None
            }
            
        except Exception as e:
            logger.error(
                f"高德地图查询异常 | "
                f"origin={origin} | "
                f"destination={destination} | "
                f"type={query_type} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"查询失败：{str(e)}"
            }

