"""LLM工厂：创建和管理LLM实例"""
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config import settings
import logging

logger = logging.getLogger(__name__)


def create_llm1() -> BaseChatModel:
    """创建主推理模型LLM1"""
    try:
        llm = ChatOpenAI(
            model=settings.llm1_model,
            temperature=settings.llm1_temperature,
            api_key=settings.llm1_api_key,
            base_url=settings.llm1_base_url,
        )
        logger.info(f"LLM1创建成功：model={settings.llm1_model}")
        return llm
    except Exception as e:
        logger.error(f"创建LLM1失败：{str(e)}", exc_info=True)
        raise


def create_llm2() -> BaseChatModel:
    """创建校验模型LLM2"""
    try:
        llm = ChatOpenAI(
            model=settings.llm2_model,
            temperature=settings.llm2_temperature,
            api_key=settings.llm2_api_key,
            base_url=settings.llm2_base_url,
        )
        logger.info(f"LLM2创建成功：model={settings.llm2_model}")
        return llm
    except Exception as e:
        logger.error(f"创建LLM2失败：{str(e)}", exc_info=True)
        raise

