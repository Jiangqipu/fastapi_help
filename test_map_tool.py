"""测试高德地图MCP工具"""
import asyncio
import logging
from app.tools.map_tool import MapQueryTool
from app.config import settings

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_map_tool():
    """测试地图工具"""
    # 从配置读取MCP服务器URL
    mcp_server_url = settings.mcp_map_server_url
    mcp_api_key = settings.mcp_map_api_key
    
    logger.info("=" * 60)
    logger.info("测试高德地图MCP工具")
    logger.info("=" * 60)
    logger.info(f"MCP服务器URL: {mcp_server_url}")
    logger.info(f"MCP API Key: {'已配置' if mcp_api_key else '未配置'}")
    logger.info(f"MCP路径前缀: {settings.mcp_map_path_prefix}")
    logger.info(f"使用SSE: {settings.mcp_use_sse}")
    logger.info("")
    
    # 创建工具实例
    tool = MapQueryTool(
        mcp_server_url=mcp_server_url,
        api_key=mcp_api_key,
        timeout=30,
        use_sse=settings.mcp_use_sse
    )
    
    # 测试1: 路线规划
    logger.info("测试1: 路线规划查询")
    logger.info("-" * 60)
    result1 = await tool.execute(
        origin="北京",
        destination="上海",
        query_type="route"
    )
    logger.info(f"结果状态: {result1.get('status')}")
    if result1.get('status') == 'success':
        logger.info(f"数据: {result1.get('data')}")
    else:
        logger.error(f"错误: {result1.get('error_message')}")
    logger.info("")
    

if __name__ == "__main__":
    asyncio.run(test_map_tool())

