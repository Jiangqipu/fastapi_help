"""FastAPI主应用"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.config import settings
from app.storage import RedisStorage
from app.llm_factory import create_llm1, create_llm2
from app.graph import build_travel_planner_graph
from app.utils.logger import setup_logging
import logging

# 配置日志（包括文件和控制台）
log_file_path = setup_logging()
logger = logging.getLogger(__name__)

if log_file_path:
    logger.info(f"日志文件已配置: {log_file_path}")

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    description="基于LangGraph的智能出行规划助手",
    version="0.1.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api/v1", tags=["travel-planner"])


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("应用启动中...")
    
    # 初始化Redis连接（使用全局存储实例）
    try:
        from app.api.routes import get_storage, ensure_storage_connected
        storage = await ensure_storage_connected()
        if storage.redis_client:
            logger.info("Redis连接成功")
        else:
            logger.warning("Redis连接未建立，但应用将继续运行")
    except Exception as e:
        logger.error(f"Redis连接失败：{str(e)}", exc_info=True)
        # 可以选择继续运行（使用内存存储）或退出
        logger.warning("继续运行，但会话持久化功能可能不可用")
    
    # 初始化LLM（可选，延迟初始化也可以）
    try:
        llm1 = create_llm1()
        llm2 = create_llm2()
        logger.info("LLM初始化成功")
    except Exception as e:
        logger.error(f"LLM初始化失败：{str(e)}", exc_info=True)
        logger.warning("LLM将在首次请求时初始化")
    
    logger.info("应用启动完成")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("应用关闭中...")
    
    # 关闭Redis连接（使用全局存储实例）
    try:
        from app.api.routes import _storage
        if _storage and _storage.redis_client:
            await _storage.disconnect()
            logger.info("Redis连接已关闭")
    except Exception as e:
        logger.error(f"关闭Redis连接失败：{str(e)}", exc_info=True)
    
    logger.info("应用已关闭")


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "智能出行规划助手API",
        "version": "0.1.0",
        "docs": "/docs"
    }

