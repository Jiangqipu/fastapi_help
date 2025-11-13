"""测试携程酒店MCP工具"""
import asyncio
import logging
from app.tools.hotel_tool import HotelQueryTool
from app.config import settings

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_hotel_tool():
    """测试酒店工具"""
    # 从配置读取MCP服务器URL
    mcp_server_url = settings.mcp_hotel_server_url
    mcp_api_key = settings.mcp_hotel_api_key
    
    logger.info("=" * 60)
    logger.info("测试携程酒店MCP工具")
    logger.info("=" * 60)
    logger.info(f"MCP服务器URL: {mcp_server_url}")
    logger.info(f"MCP API Key: {'已配置' if mcp_api_key else '未配置'}")
    logger.info(f"MCP路径前缀: {settings.mcp_hotel_path_prefix}")
    logger.info(f"使用SSE: {settings.mcp_use_sse}")
    logger.info("")
    
    if not mcp_server_url:
        logger.warning("MCP服务器URL未配置，跳过测试")
        return
    
    # 创建工具实例（使用配置的超时时间，携程可能需要更长时间）
    tool = HotelQueryTool(
        mcp_server_url=mcp_server_url,
        api_key=mcp_api_key,
        timeout=settings.mcp_hotel_timeout,  # 使用配置的超时时间（默认120秒）
        use_sse=settings.mcp_use_sse
    )
    
    # 测试1: 查询酒店
    logger.info("测试1: 查询酒店")
    logger.info("-" * 60)
    result1 = await tool.execute(
        city="上海",
        check_in="2025-01-15",
        check_out="2025-01-17"
    )
    logger.info(f"结果状态: {result1.get('status')}")
    if result1.get('status') == 'success':
        logger.info(f"数据: {result1.get('data')}")
    else:
        logger.error(f"错误: {result1.get('error_message')}")
    logger.info("")


if __name__ == "__main__":
    asyncio.run(test_hotel_tool())

