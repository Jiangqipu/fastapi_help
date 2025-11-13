"""应用配置管理模块"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # Redis配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_decode_responses: bool = True
    
    # LLM配置
    llm1_api_key: str = ""  # 主推理模型API Key
    llm1_model: str = "gpt-4"
    llm1_base_url: Optional[str] = None
    llm1_temperature: float = 0.7
    
    llm2_api_key: str = ""  # 校验模型API Key
    llm2_model: str = "gpt-4"
    llm2_base_url: Optional[str] = None
    llm2_temperature: float = 0.3
    
    # 应用配置
    app_name: str = "智能出行规划助手"
    debug: bool = False
    log_level: str = "INFO"
    
    # 日志配置
    log_dir: str = "logs"  # 日志文件目录
    log_file: str = "app.log"  # 日志文件名
    log_backup_count: int = 30  # 保留的日志文件备份数量（按天计算，默认保留30天）
    log_enable_file: bool = True  # 是否启用文件日志
    log_enable_console: bool = True  # 是否启用控制台日志
    
    # 重试配置
    max_retry_count: int = 3
    
    # 会话过期时间（秒）
    session_ttl: int = 3600
    
    # 时间约束计算默认值
    default_travel_duration_minutes: int = 120  # 默认行程耗时
    minimum_departure_buffer_minutes: int = 15  # 最小出发缓冲
    default_activity_duration_minutes: int = 30  # 默认单个活动时长
    default_activity_buffer_minutes: int = 15  # 活动之间最小缓冲

    # MCP工具配置（SSE格式）
    # 12306火车票查询工具
    mcp_train_server_url: Optional[str] = None
    mcp_train_api_key: Optional[str] = None
    mcp_train_timeout: int = 30
    
    # 高德地图查询工具
    mcp_map_server_url: Optional[str] = None
    mcp_map_api_key: Optional[str] = None
    mcp_map_timeout: int = 30
    mcp_map_path_prefix: str = "/tools"  # MCP工具路径前缀，默认为/tools
    
    # 携程酒店查询工具
    mcp_hotel_server_url: Optional[str] = None
    mcp_hotel_api_key: Optional[str] = None
    mcp_hotel_timeout: int = 300  # 携程MCP返回数据时间较长，设置为300秒（5分钟）
    
    # MCP通用配置
    mcp_use_sse: bool = True  # 是否使用SSE格式
    mcp_connection_timeout: int = 10  # 连接超时时间（秒）
    
    # MCP路径配置（可选，用于自定义路径格式）
    mcp_train_path_prefix: str = "/tools"  # 12306工具路径前缀
    mcp_hotel_path_prefix: str = "/tools"  # 酒店工具路径前缀
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()

