"""MCP客户端：支持SSE格式的MCP工具调用"""
import httpx
import json
import logging
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class MCPClient:
    """MCP客户端，支持SSE格式的流式调用"""
    
    def __init__(
        self,
        server_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        use_sse: bool = True,
        path_prefix: str = "/tools",
        api_key_in_header: bool = False
    ):
        """
        初始化MCP客户端
        
        Args:
            server_url: MCP服务器URL（基础URL，不包含路径）
            api_key: API密钥
            timeout: 超时时间（秒）
            use_sse: 是否使用SSE格式
            path_prefix: 工具路径前缀，默认为/tools
            api_key_in_header: 是否将API key放在header中（True=header, False=query参数）
        """
        # 清理server_url，移除末尾的斜杠和路径
        original_url = server_url.rstrip('/')
        
        # 检查URL是否以/mcp结尾（表示使用JSON-RPC 2.0格式）
        url_ends_with_mcp = original_url.endswith('/mcp')
        
        # 如果URL以/mcp结尾，移除它（会在请求时重新添加）
        if url_ends_with_mcp:
            self.server_url = original_url[:-4]
        else:
            self.server_url = original_url
        
        # 检查MCP服务器类型
        self.is_amap_mcp = 'amap.com' in self.server_url or 'mcp.amap.com' in self.server_url
        self.is_12306_mcp = '12306' in self.server_url or 'train' in self.server_url.lower()
        self.is_ctrip_mcp = 'ctrip.com' in self.server_url or 'ctrip' in self.server_url.lower() or 'hotel' in self.server_url.lower()
        
        # 携程默认使用header传递key
        if self.is_ctrip_mcp:
            api_key_in_header = True
        
        # 处理特殊MCP服务器的情况（使用JSON-RPC 2.0格式）
        # 如果URL以/mcp结尾，或者明确识别为特殊服务器，则使用JSON-RPC格式
        self.use_jsonrpc = url_ends_with_mcp or self.is_amap_mcp or self.is_12306_mcp or self.is_ctrip_mcp
        
        if self.use_jsonrpc:
            # JSON-RPC 2.0格式的MCP服务器：使用/mcp端点
            # 不使用path_prefix，而是使用/mcp端点
            self.path_prefix = None
        else:
            # 标准MCP：处理path_prefix
            if self.server_url.endswith('/mcp'):
                self.server_url = self.server_url[:-4]
                if not path_prefix.startswith('/mcp'):
                    self.path_prefix = f"/mcp{path_prefix}".rstrip('/')
                else:
                    self.path_prefix = path_prefix.rstrip('/')
            else:
                self.path_prefix = path_prefix.rstrip('/')
        
        self.api_key = api_key
        self.timeout = timeout
        self.use_sse = use_sse
        self.api_key_in_header = api_key_in_header
        
        # JSON-RPC格式的MCP服务器（高德、12306等）要求同时接受application/json和text/event-stream
        if self.use_jsonrpc and use_sse:
            accept_header = "application/json, text/event-stream"
        else:
            accept_header = "text/event-stream" if use_sse else "application/json"
        
        self.headers = {
            "Content-Type": "application/json",
            "Accept": accept_header
        }
        
        # 根据配置决定key的传递方式
        if api_key:
            if api_key_in_header:
                # 携程等使用header传递key
                # 检查api_key是否已经包含Bearer前缀
                if api_key.startswith("Bearer "):
                    self.headers["Authorization"] = api_key
                else:
                    self.headers["Authorization"] = f"Bearer {api_key}"
                # 或者使用X-API-Key header（根据实际需求调整）
                # self.headers["X-API-Key"] = api_key
            # 如果使用query参数（如高德），在请求时添加
        
        logger.info(
            f"MCP客户端初始化成功 | "
            f"server_url={self.server_url} | "
            f"path_prefix={self.path_prefix} | "
            f"use_sse={self.use_sse} | "
            f"jsonrpc={self.use_jsonrpc} | "
            f"key_in_header={api_key_in_header} | "
            f"timeout={self.timeout}s"
        )
    
    async def call_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用MCP工具
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
        
        Returns:
            Dict包含status和data
        """
        if not self.server_url:
            return {
                "status": "error",
                "data": None,
                "error_message": "MCP服务器URL未配置"
            }
        
        try:
            if self.use_sse:
                # 使用SSE格式
                return await self._call_with_sse(tool_name, parameters)
            else:
                # 使用普通HTTP请求
                return await self._call_with_http(tool_name, parameters)
        except httpx.ReadTimeout as e:
            logger.error(
                f"MCP工具调用超时 | "
                f"tool={tool_name} | "
                f"timeout={self.timeout}s | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"请求超时：服务器在{self.timeout}秒内未响应，可能需要更长的等待时间。当前超时设置：{self.timeout}秒"
            }
        except httpx.RequestError as e:
            logger.error(
                f"MCP工具请求错误 | "
                f"tool={tool_name} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"请求失败：{str(e)}"
            }
        except Exception as e:
            logger.error(
                f"MCP工具调用异常 | "
                f"tool={tool_name} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"调用失败：{str(e)}"
            }
    
    async def _call_with_sse(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用SSE格式调用MCP工具"""
        if self.use_jsonrpc:
            url = f"{self.server_url}/mcp"
            
            if self.api_key and not self.api_key_in_header:
                key_value = self.api_key
                if key_value.startswith("Bearer "):
                    key_value = key_value[7:]
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}key={key_value}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": parameters
                }
            }
            
            server_type = "高德" if self.is_amap_mcp else ("12306" if self.is_12306_mcp else "携程" if self.is_ctrip_mcp else "JSON-RPC")
            logger.info(
                f"{server_type}MCP请求 | "
                f"tool={tool_name} | "
                f"url={url} | "
                f"method=tools/call"
            )
        else:
            url = f"{self.server_url}{self.path_prefix}/{tool_name}"
            payload = {"tool": tool_name, "parameters": parameters}
            logger.info(f"MCP SSE请求 | tool={tool_name} | url={url}")
        
        logger.debug(f"MCP请求参数 | tool={tool_name} | payload={json.dumps(payload, ensure_ascii=False)}")
        
        from httpx import Timeout
        timeout_config = Timeout(
            connect=10.0,
            read=self.timeout,
            write=10.0,
            pool=10.0
        )
        logger.debug(f"MCP超时配置 | tool={tool_name} | connect=10s, read={self.timeout}s, write=10s, pool=10s")
        
        async with httpx.AsyncClient(timeout=timeout_config) as client:
            try:
                async with client.stream(
                    "POST",
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=timeout_config  # 确保stream也使用相同的超时配置
                ) as response:
                    logger.debug(f"MCP响应状态码 | tool={tool_name} | status={response.status_code}")
                    
                    if response.status_code != 200:
                        try:
                            error_text = ""
                            async for line in response.aiter_lines():
                                error_text += line + "\n"
                            if not error_text.strip():
                                error_text = f"HTTP {response.status_code}: {response.reason_phrase or 'Unknown error'}"
                            else:
                                error_text = f"HTTP {response.status_code}: {error_text.strip()}"
                        except Exception as e:
                            error_text = f"HTTP {response.status_code}: 无法读取错误响应 - {str(e)}"
                            logger.error(f"MCP错误响应读取失败 | tool={tool_name} | error={str(e)}", exc_info=True)
                        
                        logger.error(
                            f"MCP工具调用失败 | "
                            f"tool={tool_name} | "
                            f"status={response.status_code} | "
                            f"error={error_text[:200]}"
                        )
                        return {
                            "status": "error",
                            "data": None,
                            "error_message": error_text
                        }
                    
                    # 检查响应类型：如果是application/json，直接解析JSON；否则解析SSE流
                    content_type = response.headers.get("content-type", "").lower()
                    result_data = []
                    
                    if "application/json" in content_type and "text/event-stream" not in content_type:
                        try:
                            content = b""
                            async for chunk in response.aiter_bytes():
                                content += chunk
                            data = json.loads(content.decode('utf-8'))
                            result_data.append(data)
                            logger.debug(f"MCP JSON响应解析成功 | tool={tool_name} | data_type={type(data).__name__}")
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"MCP JSON解析失败 | "
                                f"tool={tool_name} | "
                                f"error={str(e)}",
                                exc_info=True
                            )
                            return {
                                "status": "error",
                                "data": None,
                                "error_message": f"JSON解析失败: {str(e)}"
                            }
                    else:
                        line_count = 0
                        logger.info(f"MCP开始读取SSE流 | tool={tool_name}")
                        try:
                            async for line in response.aiter_lines():
                                line_count += 1
                                if line_count <= 5 or line_count % 100 == 0:
                                    logger.debug(f"MCP SSE行 | tool={tool_name} | line={line_count} | content={line[:100]}")
                                
                                if line.startswith("data: "):
                                    data_str = line[6:]
                                    try:
                                        data = json.loads(data_str)
                                        result_data.append(data)
                                    except json.JSONDecodeError:
                                        result_data.append(data_str)
                                elif line.startswith("event: "):
                                    event_type = line[7:].strip()
                                    logger.debug(f"MCP SSE事件 | tool={tool_name} | event={event_type}")
                                elif line.strip() == "" or line.startswith(":"):
                                    continue
                        except httpx.ReadTimeout as e:
                            logger.warning(
                                f"MCP SSE流读取超时 | "
                                f"tool={tool_name} | "
                                f"lines_received={line_count} | "
                                f"data_count={len(result_data)} | "
                                f"error={str(e)}"
                            )
                            if not result_data:
                                return {
                                    "status": "error",
                                    "data": None,
                                    "error_message": f"读取超时：服务器在{self.timeout}秒内未返回数据"
                                }
                        
                        logger.info(
                            f"MCP SSE流解析完成 | "
                            f"tool={tool_name} | "
                            f"lines={line_count} | "
                            f"data_items={len(result_data)}"
                        )
                    
                    if result_data:
                        logger.debug(f"MCP数据示例 | tool={tool_name} | sample={str(result_data[0])[:200] if result_data else 'N/A'}")
                    
                    if self.use_jsonrpc and result_data:
                        final_data = None
                        for item in result_data:
                            if isinstance(item, dict):
                                if "result" in item:
                                    result_content = item.get("result", {})
                                    if "content" in result_content:
                                        content = result_content.get("content")
                                        if isinstance(content, list) and len(content) > 0:
                                            first_content = content[0]
                                            if isinstance(first_content, dict) and "text" in first_content:
                                                try:
                                                    final_data = json.loads(first_content.get("text", ""))
                                                except json.JSONDecodeError:
                                                    final_data = first_content.get("text", "")
                                            else:
                                                final_data = first_content
                                        elif isinstance(content, str):
                                            try:
                                                final_data = json.loads(content)
                                            except json.JSONDecodeError:
                                                final_data = content
                                        else:
                                            final_data = content
                                    else:
                                        final_data = result_content
                                    break
                                elif "error" in item:
                                    error_info = item.get("error", {})
                                    error_msg = error_info.get('message', 'Unknown error')
                                    logger.error(f"MCP工具返回错误 | tool={tool_name} | error={error_msg}")
                                    return {
                                        "status": "error",
                                        "data": None,
                                        "error_message": f"MCP错误: {error_msg}"
                                    }
                        
                        if final_data is None and result_data:
                            first_item = result_data[0]
                            if isinstance(first_item, dict):
                                if "result" in first_item:
                                    result_content = first_item.get("result", {})
                                    if "content" in result_content:
                                        content = result_content.get("content")
                                        if isinstance(content, list) and len(content) > 0:
                                            first_content = content[0]
                                            if isinstance(first_content, dict) and "text" in first_content:
                                                try:
                                                    final_data = json.loads(first_content.get("text", ""))
                                                except json.JSONDecodeError:
                                                    final_data = first_content.get("text", "")
                                            else:
                                                final_data = first_content
                                        else:
                                            final_data = content
                                    else:
                                        final_data = result_content
                                else:
                                    final_data = first_item
                            else:
                                final_data = first_item
                    else:
                        if len(result_data) == 0:
                            logger.warning(f"MCP SSE流中没有有效数据 | tool={tool_name}")
                            return {
                                "status": "error",
                                "data": None,
                                "error_message": "SSE流中没有有效数据"
                            }
                        elif len(result_data) == 1:
                            final_data = result_data[0]
                        else:
                            final_data = result_data
                    
                    if final_data is None:
                        logger.warning(f"MCP无法提取有效数据 | tool={tool_name} | data_count={len(result_data)}")
                        return {
                            "status": "error",
                            "data": None,
                            "error_message": "无法从响应中提取有效数据"
                        }
                    
                    # 记录返回数据（完整记录）
                    try:
                        data_json = json.dumps(final_data, ensure_ascii=False, indent=2)
                        logger.info(
                            f"MCP工具调用成功 | "
                            f"tool={tool_name} | "
                            f"data_type={type(final_data).__name__} | "
                            f"data_size={len(data_json)} | "
                            f"data={data_json}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"MCP工具返回数据序列化失败 | "
                            f"tool={tool_name} | "
                            f"data_type={type(final_data).__name__} | "
                            f"error={str(e)}"
                        )
                        logger.info(
                            f"MCP工具调用成功 | "
                            f"tool={tool_name} | "
                            f"data_type={type(final_data).__name__} | "
                            f"data_repr={str(final_data)}"
                        )
                    
                    return {
                        "status": "success",
                        "data": final_data,
                        "error_message": None
                    }
            except httpx.ReadTimeout as e:
                logger.error(
                    f"MCP SSE流建立超时 | "
                    f"tool={tool_name} | "
                    f"timeout={self.timeout}s | "
                    f"error={str(e)}",
                    exc_info=True
                )
                return {
                    "status": "error",
                    "data": None,
                    "error_message": f"连接超时：服务器在{self.timeout}秒内未返回响应头，可能需要更长的等待时间"
                }
            except httpx.RequestError as e:
                logger.error(
                    f"MCP SSE流请求错误 | "
                    f"tool={tool_name} | "
                    f"error={str(e)}",
                    exc_info=True
                )
                return {
                    "status": "error",
                    "data": None,
                    "error_message": f"请求失败：{str(e)}"
                }
            except Exception as e:
                logger.error(
                    f"MCP SSE流调用异常 | "
                    f"tool={tool_name} | "
                    f"error={str(e)}",
                    exc_info=True
                )
                return {
                    "status": "error",
                    "data": None,
                    "error_message": f"调用失败：{str(e)}"
                }
    
    async def _call_with_http(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用普通HTTP请求调用MCP工具"""
        if self.use_jsonrpc:
            url = f"{self.server_url}/mcp"
            if self.api_key and not self.api_key_in_header:
                key_value = self.api_key
                if key_value.startswith("Bearer "):
                    key_value = key_value[7:]
                url = f"{url}?key={key_value}"
            
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": parameters
                }
            }
        else:
            url = f"{self.server_url}{self.path_prefix}/{tool_name}"
            payload = {
                "tool": tool_name,
                "parameters": parameters
            }
        
        logger.info(f"MCP HTTP请求 | tool={tool_name} | url={url}")
        logger.debug(f"MCP请求参数 | tool={tool_name} | payload={json.dumps(payload, ensure_ascii=False)}")
        
        from httpx import Timeout
        timeout_config = Timeout(
            connect=10.0,
            read=self.timeout,
            write=10.0,
            pool=10.0
        )
        
        try:
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                
                logger.debug(f"MCP HTTP响应 | tool={tool_name} | status={response.status_code}")
                
                if response.status_code != 200:
                    logger.error(
                        f"MCP HTTP请求失败 | "
                        f"tool={tool_name} | "
                        f"status={response.status_code} | "
                        f"response={response.text[:200]}"
                    )
                    return {
                        "status": "error",
                        "data": None,
                        "error_message": f"HTTP {response.status_code}: {response.text}"
                    }
                
                try:
                    data = response.json()
                    
                    if self.use_jsonrpc and isinstance(data, dict):
                        if "result" in data:
                            result_content = data.get("result", {})
                            if "content" in result_content:
                                content = result_content.get("content")
                                if isinstance(content, list) and len(content) > 0:
                                    first_content = content[0]
                                    if isinstance(first_content, dict) and "text" in first_content:
                                        try:
                                            data = json.loads(first_content.get("text", ""))
                                        except json.JSONDecodeError:
                                            data = first_content.get("text", "")
                                    else:
                                        data = first_content
                                elif isinstance(content, str):
                                    try:
                                        data = json.loads(content)
                                    except json.JSONDecodeError:
                                        data = content
                                else:
                                    data = content
                            else:
                                data = result_content
                        elif "error" in data:
                            error_info = data.get("error", {})
                            error_msg = error_info.get('message', 'Unknown error')
                            logger.error(f"MCP工具返回错误 | tool={tool_name} | error={error_msg}")
                            return {
                                "status": "error",
                                "data": None,
                                "error_message": f"MCP错误: {error_msg}"
                            }
                    
                    # 记录返回数据（完整记录）
                    try:
                        data_json = json.dumps(data, ensure_ascii=False, indent=2)
                        logger.info(
                            f"MCP HTTP工具调用成功 | "
                            f"tool={tool_name} | "
                            f"data_type={type(data).__name__} | "
                            f"data_size={len(data_json)} | "
                            f"data={data_json}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"MCP HTTP工具返回数据序列化失败 | "
                            f"tool={tool_name} | "
                            f"data_type={type(data).__name__} | "
                            f"error={str(e)}"
                        )
                        logger.info(
                            f"MCP HTTP工具调用成功 | "
                            f"tool={tool_name} | "
                            f"data_type={type(data).__name__} | "
                            f"data_repr={str(data)}"
                        )
                    
                    return {
                        "status": "success",
                        "data": data,
                        "error_message": None
                    }
                except json.JSONDecodeError as e:
                    logger.error(
                        f"MCP JSON解析失败 | "
                        f"tool={tool_name} | "
                        f"error={str(e)}",
                        exc_info=True
                    )
                    return {
                        "status": "error",
                        "data": None,
                        "error_message": "响应不是有效的JSON格式"
                    }
        except httpx.ReadTimeout as e:
            logger.error(
                f"MCP HTTP请求超时 | "
                f"tool={tool_name} | "
                f"timeout={self.timeout}s | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"请求超时：服务器在{self.timeout}秒内未响应"
            }
        except Exception as e:
            logger.error(
                f"MCP HTTP请求异常 | "
                f"tool={tool_name} | "
                f"error={str(e)}",
                exc_info=True
            )
            return {
                "status": "error",
                "data": None,
                "error_message": f"请求失败：{str(e)}"
            }

