# 🚀 智能出行规划助手

基于 LangGraph 的智能出行规划助手，通过多轮交互、槽位填充和多工具调用（MCP），为用户提供完整、准确的行程和住宿规划。

## ✨ 特性

- **多轮交互**：通过 LangGraph 实现智能的槽位填充和校验循环
- **工具集成**：支持 12306、高德地图、携程等 MCP 工具
- **会话持久化**：使用 Redis 存储用户会话和状态
- **智能校验**：使用双 LLM 模型进行槽位校验和结果校验
- **动态指令**：支持在工具调用时插入动态指令
- **智能参数修正**：自动检测并修正工具调用参数错误（如日期错误）
- **日期验证**：自动验证和修正日期参数，确保日期合理
- **健壮性**：完善的错误处理、重试机制和参数修正流程

## 📋 项目结构

```
fastapi_help/
├── app/
│   ├── __init__.py
│   ├── config.py              # 配置管理
│   ├── llm_factory.py         # LLM 工厂
│   ├── api/                   # FastAPI 路由
│   │   ├── main.py
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── models/                 # 数据模型
│   │   └── state.py
│   ├── tools/                  # MCP 工具
│   │   ├── __init__.py
│   │   ├── base.py             # MCP工具基类
│   │   ├── mcp_client.py       # MCP客户端
│   │   ├── train_tool.py       # 12306火车票查询工具
│   │   ├── map_tool.py         # 高德地图查询工具
│   │   └── hotel_tool.py       # 携程酒店查询工具
│   ├── graph/                  # LangGraph 流程
│   │   ├── nodes.py
│   │   └── graph_builder.py
│   ├── prompts/                # 提示词模板
│   │   └── prompt_templates.py
│   ├── storage/                # 存储管理
│   │   └── redis_storage.py
│   └── utils/                  # 工具函数
│       ├── logger.py
│       └── exceptions.py
├── logs/                       # 日志文件目录
│   ├── app.log                 # 当前日志文件
│   └── app.log.YYYY-MM-DD      # 历史日志文件（按日期）
├── examples/                   # 使用示例
│   └── example_usage.py        # API使用示例
├── test_*.py                   # 工具测试脚本
├── main.py                     # 应用入口
├── pyproject.toml             # 项目配置
├── requirements.txt            # Python依赖
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

主要配置项：
- **Redis配置**：
  - `REDIS_HOST`: Redis 主机地址（默认：localhost）
  - `REDIS_PORT`: Redis 端口（默认：6379）
  - `REDIS_DB`: Redis 数据库编号（默认：0）
- **LLM配置**：
  - `LLM1_API_KEY`: 主推理模型 API Key
  - `LLM2_API_KEY`: 校验模型 API Key
  - `LLM1_MODEL`: 主推理模型名称（如 deepseek-chat）
  - `LLM2_MODEL`: 校验模型名称（如 deepseek-chat）
  - `LLM1_BASE_URL`: LLM1 API 基础URL
  - `LLM2_BASE_URL`: LLM2 API 基础URL
- **MCP工具配置**：
  - `MCP_TRAIN_SERVER_URL`: 12306 MCP 服务器地址
  - `MCP_TRAIN_API_KEY`: 12306 API Key
  - `MCP_MAP_SERVER_URL`: 高德地图 MCP 服务器地址
  - `MCP_MAP_API_KEY`: 高德地图 API Key
  - `MCP_HOTEL_SERVER_URL`: 携程 MCP 服务器地址
  - `MCP_HOTEL_API_KEY`: 携程 API Key
  - `MCP_USE_SSE`: 是否使用 SSE 格式（默认：true）
  - `MCP_HOTEL_TIMEOUT`: 携程工具超时时间（秒，默认：300）

### 3. 启动 Redis

```bash
# 使用 Docker
docker run -d -p 6379:6379 redis:latest

# 或使用本地 Redis
redis-server
```

### 4. 启动应用

```bash
python main.py
```

应用将在 `http://localhost:8000` 启动。

### 5. 访问 API 文档

打开浏览器访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 📖 API 使用示例

### 创建出行规划

```bash
curl -X POST "http://localhost:8000/api/v1/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "user_input": "我想从北京去上海，1月15日出发，2个人"
  }'
```

### 继续对话（补充信息）

```bash
curl -X POST "http://localhost:8000/api/v1/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "user_input": "1月17日返回，住五星级酒店"
  }'
```

### 获取用户状态

```bash
curl "http://localhost:8000/api/v1/state/user123"
```

### 清除用户状态

```bash
curl -X DELETE "http://localhost:8000/api/v1/state/user123"
```

## 📝 日志配置

项目支持同时输出日志到控制台和文件：

- **日志文件位置**：`logs/app.log`
- **日志轮转**：按日期分割，每天午夜自动创建新日志文件，保留 30 天的历史日志
- **日志级别**：通过 `.env` 文件中的 `LOG_LEVEL` 配置（默认：INFO）
- **日志格式**：`时间 - 模块名 - 级别 - 消息`
- **数据记录**：工具返回的完整数据都会记录到日志文件中

日志文件命名规则：
- 当前日志：`logs/app.log`
- 历史日志：`logs/app.log.2025-01-15`（按日期命名）

日志配置项（可在 `.env` 中配置）：
- `LOG_DIR`: 日志目录（默认：`logs`）
- `LOG_FILE`: 日志文件名（默认：`app.log`）
- `LOG_BACKUP_COUNT`: 保留的历史日志文件数量（默认：30，即保留30天）
- `LOG_ENABLE_FILE`: 是否启用文件日志（默认：`true`）
- `LOG_ENABLE_CONSOLE`: 是否启用控制台日志（默认：`true`）

## 🔧 核心流程

### 第一阶段：槽位填充与校验循环

1. **Initial_Input**: 接收用户输入，更新对话历史
2. **Intent_Decompose_LLM1**: 使用 LLM1 进行意图分解和槽位填充
3. **Slot_Validation_LLM2**: 使用 LLM2 校验槽位完整性和合理性
4. **User_Refinement**: 如果校验不通过，生成友好提示，返回第一步

### 第二阶段：任务执行与结果整合

1. **Task_Decomposition_LLM1**: 根据完整槽位分解任务
2. **Tool_Execution_MCP**: 
   - 执行工具调用前自动验证和修正日期参数
   - 调用 MCP 工具（支持并行）
   - 记录完整的工具返回数据到日志
3. **Result_Validation_LLM2**: 校验工具返回结果的有效性
4. **Parameter_Correction_LLM1**（可选）: 
   - 如果检测到参数错误（如日期错误），使用 LLM1 修正参数
   - 修正后重新执行工具
5. **Task_Scheduler**: 根据校验结果决定重试、继续或进入最终整合
6. **Final_Integration_LLM1**: 整合所有结果，生成最终方案

### 智能优化特性

- **日期自动修正**：工具执行前自动检测并修正过去的日期为未来日期
- **参数智能修正**：当工具返回参数错误时，使用 LLM 分析错误并自动修正参数
- **重试机制**：最多重试 3 次，每次重试前会尝试修正参数
- **完整日志**：所有工具调用和返回数据都完整记录到日志文件

## 🛠️ 扩展工具

要添加新的 MCP 工具，只需：

1. 继承 `BaseMCPTool` 类
2. 实现 `_arun` 方法（LangChain Tool 接口）
3. 可选：实现 `execute` 方法（兼容旧接口）
4. 在 `app/graph/nodes.py` 的 `get_tool_registry()` 函数中注册工具

示例：

```python
from app.tools.base import BaseMCPTool
from typing import Dict, Any
import json

class MyCustomTool(BaseMCPTool):
    name = "my_tool"
    description = "我的自定义工具"
    
    def __init__(self, **kwargs):
        super().__init__(
            mcp_server_url="https://api.example.com",
            api_key="your_api_key",
            timeout=30,
            use_sse=True,
            **kwargs
        )
    
    async def _arun(self, **kwargs) -> str:
        """LangChain Tool 接口：异步执行工具"""
        result = await self.execute(**kwargs)
        return json.dumps(result, ensure_ascii=False)
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具查询并返回结果"""
        # 使用 self.mcp_client 调用 MCP 服务器
        if self.mcp_client:
            result = await self.mcp_client.call_tool(
                tool_name="my_tool",
                parameters=kwargs
            )
            return result
        else:
            # 模拟数据
            return {
                "status": "success",
                "data": {"result": "mock data"},
                "error_message": None
            }
```

然后在 `app/graph/nodes.py` 的 `get_tool_registry()` 函数中注册：

```python
def get_tool_registry() -> Dict[str, BaseMCPTool]:
    return {
        "train_query": TrainQueryTool(...),
        "map_query": MapQueryTool(...),
        "hotel_query": HotelQueryTool(...),
        "my_tool": MyCustomTool(...),  # 添加新工具
    }
```

## 🧪 测试工具

项目提供了独立的测试脚本用于测试各个 MCP 工具：

```bash
# 测试12306火车票查询工具
uv run python test_train_tool.py

# 测试高德地图查询工具
uv run python test_map_tool.py

# 测试携程酒店查询工具
uv run python test_hotel_tool.py
```

这些测试脚本会直接调用工具并输出结果，方便调试和验证工具配置。

## 📝 注意事项

1. **API Key**: 确保配置了有效的 LLM API Key 和 MCP 工具 API Key
2. **Redis**: 确保 Redis 服务正在运行（如果未连接，应用会降级运行但无法持久化状态）
3. **日期格式**: 所有日期必须使用 `YYYY-MM-DD` 格式，系统会自动验证和修正日期
4. **超时设置**: 携程工具响应较慢，默认超时时间为 300 秒，可在 `.env` 中配置
5. **日志文件**: 日志文件按日期自动分割，建议定期清理旧日志文件
6. **错误处理**: 应用包含完善的错误处理、重试和参数修正机制
7. **生产环境**: 建议在生产环境中添加监控、告警和认证机制

## 🔒 安全性

- 生产环境应限制 CORS 来源
- API Key 应通过环境变量管理，不要提交到代码仓库
- 建议使用 HTTPS
- 添加认证和授权机制

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
