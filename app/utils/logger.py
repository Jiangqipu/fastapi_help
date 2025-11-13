"""日志工具"""
import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from app.config import settings


def setup_logging():
    """配置全局日志系统"""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    handlers = []
    
    # 控制台日志
    if settings.log_enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(log_level)
        handlers.append(console_handler)
    
    # 文件日志
    if settings.log_enable_file:
        # 创建日志目录
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # 日志文件路径
        log_file_path = log_dir / settings.log_file
        
        # 使用TimedRotatingFileHandler按日期分割日志
        # when='midnight' 表示每天午夜轮转
        # interval=1 表示每1天轮转一次
        # backupCount 表示保留的备份文件数量
        file_handler = TimedRotatingFileHandler(
            log_file_path,
            when='midnight',
            interval=1,
            backupCount=settings.log_backup_count,
            encoding='utf-8',
            utc=False  # 使用本地时间
        )
        # 设置后缀格式为日期（例如：app.log.2025-01-15）
        file_handler.suffix = '%Y-%m-%d'
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        handlers.append(file_handler)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
        force=True  # 强制重新配置，覆盖之前的配置
    )
    
    return log_dir / settings.log_file if settings.log_enable_file else None

