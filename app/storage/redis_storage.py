"""Redis会话存储管理器"""
import json
import redis.asyncio as redis
from typing import Optional, Dict, Any, List
import logging
from app.config import settings

logger = logging.getLogger(__name__)


class RedisStorage:
    """Redis存储管理器，用于存储Graph State和会话历史"""
    
    def __init__(self):
        """初始化Redis连接"""
        self.redis_client: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
    
    async def connect(self):
        """建立Redis连接"""
        try:
            self._connection_pool = redis.ConnectionPool(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=settings.redis_decode_responses,
                max_connections=50
            )
            self.redis_client = redis.Redis(connection_pool=self._connection_pool)
            # 测试连接
            await self.redis_client.ping()
            logger.info("Redis连接成功")
        except Exception as e:
            logger.error(f"Redis连接失败：{str(e)}", exc_info=True)
            raise
    
    async def disconnect(self):
        """关闭Redis连接"""
        if self.redis_client:
            await self.redis_client.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        logger.info("Redis连接已关闭")
    
    def _get_state_key(self, user_id: str) -> str:
        """获取状态存储的Key"""
        return f"travel_planner:state:{user_id}"
    
    def _get_history_key(self, user_id: str) -> str:
        """获取历史记录存储的Key"""
        return f"travel_planner:history:{user_id}"
    
    async def save_state(self, user_id: str, state: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        保存Graph State
        
        Args:
            user_id: 用户ID
            state: 状态字典
            ttl: 过期时间（秒），None则使用默认值
        
        Returns:
            bool: 是否保存成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法保存状态")
            return False
        
        try:
            key = self._get_state_key(user_id)
            # 序列化状态
            state_json = json.dumps(state, ensure_ascii=False)
            ttl = ttl or settings.session_ttl
            await self.redis_client.setex(key, ttl, state_json)
            logger.debug(f"保存状态成功：user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"保存状态失败：{str(e)}", exc_info=True)
            return False
    
    async def load_state(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        加载Graph State
        
        Args:
            user_id: 用户ID
        
        Returns:
            Optional[Dict]: 状态字典，如果不存在则返回None
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法加载状态，返回None")
            return None
        
        try:
            key = self._get_state_key(user_id)
            state_json = await self.redis_client.get(key)
            if state_json is None:
                return None
            state = json.loads(state_json)
            logger.debug(f"加载状态成功：user_id={user_id}")
            return state
        except Exception as e:
            logger.error(f"加载状态失败：{str(e)}", exc_info=True)
            return None
    
    async def delete_state(self, user_id: str) -> bool:
        """
        删除Graph State
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否删除成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法删除状态")
            return False
        
        try:
            key = self._get_state_key(user_id)
            await self.redis_client.delete(key)
            logger.debug(f"删除状态成功：user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"删除状态失败：{str(e)}", exc_info=True)
            return False
    
    async def append_history(self, user_id: str, message: Dict[str, Any]) -> bool:
        """
        追加对话历史
        
        Args:
            user_id: 用户ID
            message: 消息字典，通常包含role和content
        
        Returns:
            bool: 是否追加成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法追加历史")
            return False
        
        try:
            key = self._get_history_key(user_id)
            message_json = json.dumps(message, ensure_ascii=False)
            await self.redis_client.rpush(key, message_json)
            await self.redis_client.expire(key, settings.session_ttl)
            logger.debug(f"追加历史成功：user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"追加历史失败：{str(e)}", exc_info=True)
            return False
    
    async def get_history(self, user_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取对话历史
        
        Args:
            user_id: 用户ID
            limit: 限制返回数量，None则返回全部
        
        Returns:
            list: 历史记录列表
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法获取历史")
            return []
        
        try:
            key = self._get_history_key(user_id)
            if limit:
                messages_json = await self.redis_client.lrange(key, -limit, -1)
            else:
                messages_json = await self.redis_client.lrange(key, 0, -1)
            
            history = [json.loads(msg) for msg in messages_json]
            logger.debug(f"获取历史成功：user_id={user_id}, count={len(history)}")
            return history
        except Exception as e:
            logger.error(f"获取历史失败：{str(e)}", exc_info=True)
            return []
    
    async def clear_history(self, user_id: str) -> bool:
        """
        清空对话历史
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否清空成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法清空历史")
            return False
        
        try:
            key = self._get_history_key(user_id)
            await self.redis_client.delete(key)
            logger.debug(f"清空历史成功：user_id={user_id}")
            return True
        except Exception as e:
            logger.error(f"清空历史失败：{str(e)}", exc_info=True)
            return False

