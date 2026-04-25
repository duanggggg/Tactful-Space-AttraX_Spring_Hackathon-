# LLM Agent 集成指南

## 📌 概述

本项目已集成本地大模型接口支持，可以通过MCP协议与localhost:12345的LLM服务通信。

## 🎯 工作流程

```
MCP 客户端
    ↓
WebSocket
    ↓
mcp_pipe.py (管道)
    ↓
├─ calculator.py (计算工具)
└─ llm_agent.py (LLM代理工具) ← 新增
    ↓
本地大模型 (localhost:12345)
    ↓
返回结果给客户端
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

其中已包含：
- `aiohttp>=3.9.0` - 异步HTTP客户端
- `fastmcp>=2.13.0.2` - MCP框架
- 其他依赖项

### 2. 配置LLM服务

创建 `.env` 文件（可选）：

```
# LLM服务配置
LLM_BASE_URL=http://localhost:12345
LLM_MODEL=default
LLM_TIMEOUT=30
```

### 3. 启动MCP管道

```bash
# 启动所有配置的MCP服务（包括计算器和LLM代理）
python mcp_pipe.py

# 或只启动LLM代理
python mcp_pipe.py local-llm-agent

# 或只启动计算器
python mcp_pipe.py local-stdio-calculator
```

### 4. 在MCP客户端中使用

#### 方式A：直接调用ask_llm工具

```json
{
  "type": "tool_use",
  "name": "ask_llm",
  "arguments": {
    "question": "什么是MCP协议？",
    "chat_mode": "chat"
  }
}
```

#### 方式B：带上下文的查询

```json
{
  "name": "ask_llm_with_context",
  "arguments": {
    "question": "如何优化这段代码？",
    "context": "这是一个Python函数，用于计算阶乘",
    "chat_mode": "chat"
  }
}
```

#### 方式C：代码补全

```json
{
  "name": "llm_code_completion",
  "arguments": {
    "code_prefix": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return"
  }
}
```

#### 方式D：指令分析

```json
{
  "name": "llm_analyze_instruction",
  "arguments": {
    "instruction": "使用calculator工具计算sqrt(16)的结果"
  }
}
```

## 📋 可用工具

### 1. `ask_llm` - 基础LLM查询

**参数：**
- `question` (str): 用户问题或提示词
- `chat_mode` (str, 可选): 
  - `"chat"` (默认) - 使用chat接口
  - `"completion"` - 使用completion接口
  - `"generate"` - 使用通用generate接口

**返回值：**
```json
{
  "success": true,
  "mode": "chat",
  "question": "...",
  "response": "LLM的回复内容"
}
```

### 2. `ask_llm_with_context` - 带上下文的查询

**参数：**
- `question` (str): 用户问题
- `context` (str, 可选): 背景信息
- `chat_mode` (str, 可选): 同上

**用途：** 需要背景信息的复杂查询

### 3. `llm_code_completion` - 代码补全

**参数：**
- `code_prefix` (str): 代码片段前缀

**返回值：**
```json
{
  "success": true,
  "prefix": "代码前缀",
  "completion": "补全的代码"
}
```

### 4. `llm_analyze_instruction` - 指令分析

**参数：**
- `instruction` (str): 需要分析的MCP指令

**返回值：**
```json
{
  "success": true,
  "instruction": "原始指令",
  "analysis": "LLM的分析结果"
}
```

## 🔧 高级配置

### 修改LLM接口

编辑 `llm_agent.py`：

```python
# 修改这些常量以适配您的LLM服务
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions",           # 聊天接口
    "completion": "/v1/completions",          # 补全接口
    "generate": "/api/generate"               # 生成接口
}
```

### 自定义LLM客户端参数

在 `llm_agent.py` 中修改 `get_llm_client()` 函数：

```python
def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(
            base_url="http://localhost:12345",  # 修改端口
            timeout=60                          # 修改超时时间
        )
    return _llm_client
```

### 添加自定义工具

在 `llm_agent.py` 中添加新的 `@mcp.tool()` 装饰器方法：

```python
@mcp.tool()
async def my_custom_tool(param: str) -> dict:
    """工具描述"""
    client = get_llm_client()
    response = await client.chat([{"role": "user", "content": param}])
    return {"result": response}
```

## 🧪 测试

### 1. 检查LLM服务连接

```python
# 在Python环境中测试
import asyncio
from llm_agent import get_llm_client

async def test():
    client = get_llm_client()
    is_healthy = await client.health_check()
    print(f"LLM服务健康: {is_healthy}")
    if is_healthy:
        response = await client.chat([{"role": "user", "content": "Hello"}])
        print(f"响应: {response}")
    await client.close()

asyncio.run(test())
```

### 2. 使用MCP客户端测试

启动MCP管道后，通过MCP客户端调用工具：

```bash
python mcp_pipe.py
# 然后在另一个终端通过MCP客户端发送请求
```

## 📊 多模型支持

本实现支持多种LLM服务：

| 模型服务 | 推荐接口 | 示例 |
|---------|---------|------|
| OpenAI兼容 | `/v1/chat/completions` | chat_mode="chat" |
| Ollama | `/api/generate` | chat_mode="generate" |
| LM Studio | `/v1/chat/completions` | chat_mode="chat" |
| LocalAI | `/v1/chat/completions` | chat_mode="chat" |
| Text Generation WebUI | `/api/v1/generate` | 需要自定义 |

## 🐛 故障排查

### 问题1：无法连接到localhost:12345

**解决方案：**
```bash
# 检查LLM服务是否运行
netstat -ano | findstr :12345  # Windows
lsof -i :12345                 # Linux/Mac

# 检查防火墙设置
# 确保localhost:12345可访问
```

### 问题2：LLM响应超时

**解决方案：**
```python
# 增加超时时间
client = LLMClient(base_url="http://localhost:12345", timeout=60)
```

### 问题3：响应格式错误

**解决方案：**
根据您的LLM服务，可能需要修改 `LLM_ENDPOINTS` 中的接口地址：

```python
# 对于Ollama
LLM_ENDPOINTS = {
    "generate": "/api/generate"
}

# 对于OpenAI兼容
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions"
}
```

## 📚 架构设计

### LLMClient 类

```
LLMClient
├── __init__(base_url, timeout)
├── _get_session()              # 管理aiohttp会话
├── health_check()              # 检查服务健康
├── chat()                       # Chat API调用
├── completion()                 # Completion API调用
└── generate()                   # 通用生成API
```

### MCP工具

- 每个工具都是异步的（async）
- 自动错误处理和日志记录
- 支持超时和重试机制

## 🔐 安全建议

1. **环境变量管理**
   ```bash
   # 使用 .env 文件而不是硬编码
   export LLM_API_KEY=your_key
   ```

2. **请求验证**
   ```python
   # 在 llm_agent.py 中添加authentication
   headers = {"Authorization": f"Bearer {api_key}"}
   ```

3. **速率限制**
   ```python
   # 添加请求限流
   from aiolimiter import AsyncLimiter
   limiter = AsyncLimiter(max_rate=10, time_period=60)
   ```

## 📝 日志

默认日志级别为 `INFO`，修改方法：

```python
# 在 llm_agent.py 中
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG获取更详细信息
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## 🔄 工作流示例

### 完整流程：问答系统

1. MCP客户端 → "如何优化Python代码？"
2. mcp_pipe.py 转发给 llm_agent.py
3. LLMClient 调用 ask_llm() 
4. HTTP请求发送至 localhost:12345
5. LLM返回优化建议
6. 结果返回给客户端

### 复杂流程：指令执行

1. 客户端发送指令："计算sqrt(16)并解释结果"
2. llm_analyze_instruction() 通过LLM分析指令
3. LLM建议：使用calculator工具计算，然后解释
4. 系统执行calculator工具获得结果：4.0
5. 再次调用LLM生成解释
6. 返回完整结果给客户端

## 💡 最佳实践

1. **使用带上下文的查询**
   ```python
   ask_llm_with_context(
       question="这段代码有什么问题？",
       context="def fib(n): return fib(n-1)+fib(n-2)  # 质数检查"
   )
   ```

2. **合理选择chat_mode**
   - chat → 对话和推理任务
   - completion → 代码和文本补全
   - generate → 文本生成和摘要

3. **添加错误处理**
   ```python
   result = await ask_llm("question")
   if result["success"]:
       print(result["response"])
   else:
       print(f"错误: {result['error']}")
   ```

4. **使用健康检查**
   ```python
   if await client.health_check():
       # 执行查询
   else:
       # 备用方案或报错
   ```

## 📚 更多资源

- [MCP文档](https://modelcontextprotocol.io/)
- [FastMCP文档](https://github.com/jlopp/fastmcp)
- [Ollama文档](https://ollama.ai/) (本地LLM服务推荐)
- [LM Studio](https://lmstudio.ai/) (GUI本地LLM)

---

**需要帮助？** 检查日志输出或提出问题！
