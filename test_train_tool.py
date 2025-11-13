"""测试12306火车票MCP工具"""
import asyncio
import logging
from app.tools.train_tool import TrainQueryTool
from app.config import settings

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def test_train_tool():
    """测试火车票工具"""
    # 从配置读取MCP服务器URL
    mcp_server_url = settings.mcp_train_server_url
    mcp_api_key = settings.mcp_train_api_key
    
    logger.info("=" * 60)
    logger.info("测试12306火车票MCP工具")
    logger.info("=" * 60)
    logger.info(f"MCP服务器URL: {mcp_server_url}")
    logger.info(f"MCP API Key: {'已配置' if mcp_api_key else '未配置'}")
    logger.info(f"MCP路径前缀: {settings.mcp_train_path_prefix}")
    logger.info(f"使用SSE: {settings.mcp_use_sse}")
    logger.info("")
    
    if not mcp_server_url:
        logger.warning("MCP服务器URL未配置，跳过测试")
        return
    
    # 创建工具实例
    tool = TrainQueryTool(
        mcp_server_url=mcp_server_url,
        api_key=mcp_api_key,
        timeout=30,
        use_sse=settings.mcp_use_sse
    )
    
    # 测试1: 查询火车票（使用明天的日期）
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    logger.info("测试1: 查询火车票")
    logger.info("-" * 60)
    logger.info(f"查询日期: {tomorrow}")
    result1 = await tool.execute(
        origin="北京",
        destination="上海",
        date=tomorrow
    )
    logger.info(f"结果状态: {result1.get('status')}")
    if result1.get('status') == 'success':
        logger.info(f"数据: {result1.get('data')}")
    else:
        logger.error(f"错误: {result1.get('error_message')}")
    logger.info("")


if __name__ == "__main__":
    asyncio.run(test_train_tool())

