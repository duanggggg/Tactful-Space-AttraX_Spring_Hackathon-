# MCP + 本地大模型集成完整指南

## 📌 快速总结

您的需求：**获取MCP指令 → 转发给本地大模型(localhost:12345) → 返回结果给客户端**

### ✅ 已为您实现的内容

```
项目结构 (d:\代码\homellm\mcp\)
├── calculator.py              # 计算器工具（已有）
├── mcp_pipe.py               # MCP管道（已有）
│
├── llm_agent.py              # ✨ 新增：LLM代理模块
│   ├── LLMClient类           # 与localhost:12345通信
│   ├── ask_llm()             # 基础LLM查询工具
│   ├── ask_llm_with_context()# 带上下文的查询工具
│   ├── llm_code_completion() # 代码补全工具
│   └── llm_analyze_instruction() # 指令分析工具
│
├── mcp_config.json           # ✨ 已更新：添加LLM服务配置
├── requirements.txt          # ✨ 已更新：添加aiohttp依赖
│
├── LLM_AGENT_GUIDE.md        # ✨ 新增：详细使用指南
├── LOCAL_LLM_CONFIG.md       # ✨ 新增：本地LLM配置大全
├── examples.py               # ✨ 新增：7个实际使用示例
└── IMPLEMENTATION_GUIDE.md   # ✨ 本文件
```

---

## 🚀 5分钟快速启动

### 步骤1：安装依赖

```bash
cd d:\代码\homellm\mcp
pip install -r requirements.txt
```

### 步骤2：启动本地LLM（选择一种）

#### 方案A：Ollama（推荐，最简单）
```bash
# 1. 下载安装 https://ollama.ai
# 2. 运行以下命令启动
ollama pull mistral
ollama serve --addr 127.0.0.1:12345
```

#### 方案B：LM Studio
1. 下载/安装 https://lmstudio.ai
2. 打开应用，下载一个模型
3. 在Server标签页配置端口为12345

#### 方案C：其他服务（localhost:12345）
- Text Generation WebUI
- LocalAI
- llama.cpp
- vLLM
等等...

### 步骤3：启动MCP管道

```bash
# 启动所有服务（计算器 + LLM代理）
python mcp_pipe.py

# 或只启动LLM代理
python mcp_pipe.py local-llm-agent
```

### 步骤4：通过MCP客户端使用

MCP客户端现在可以调用这些工具：
- `ask_llm` - 询问LLM
- `ask_llm_with_context` - 带上下文的查询
- `llm_code_completion` - 代码补全
- `llm_analyze_instruction` - 指令分析

---

## 🔄 完整工作流程

```
┌─────────────────────────────────────────────────────────────┐
│  MCP 客户端 (Claude, Copilot等)                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ 发送指令
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  WebSocket 连接                                             │
│  (MCP_ENDPOINT)                                            │
└──────────────────────┬──────────────────────────────────────┘
                       │ 转发
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  mcp_pipe.py (MCP管道)                                     │
│  ├─ 接收WebSocket消息                                     │
│  ├─ 路由到对应MCP服务                                     │
│  └─ 返回结果给客户端                                     │
└──────────┬──────────────────────────────┬──────────────────┘
           │                              │
    ┌──────▼─────┐             ┌──────────▼─────┐
    │ calculator  │             │  llm_agent.py  │◄─── ✨ 新增
    │   (stdio)   │             │    (stdio)      │
    └─────────────┘             └──────┬─────────┘
    数学计算工具                        │
                                ┌──────▼──────────────┐
                                │  LLMClient 类      │◄─── 关键
                                │ (aiohttp异步客户端) │
                                └──────┬──────────────┘
                                       │ HTTP请求
                                ┌──────▼──────────────┐
                                │ localhost:12345    │◄─── 本地LLM
                                │ (Ollama/LM Studio) │
                                └────────────────────┘
                                本地大模型推理
```

---

## 📚 4种使用方式对比

| 场景 | 使用工具 | 示例 |
|------|---------|------|
| **问答对话** | `ask_llm` | "解释Python中的装饰器" |
| **需要背景** | `ask_llm_with_context` | "这段代码有什么问题？" + 代码片段 |
| **代码补全** | `llm_code_completion` | 补全Python函数 |
| **指令分析** | `llm_analyze_instruction` | 分析MCP指令的执行方案 |

### 示例JSON请求

```json
{
  "type": "tool_use",
  "name": "ask_llm",
  "arguments": {
    "question": "如何优化Python代码的性能？",
    "chat_mode": "chat"
  }
}
```

---

## 🔧 配置说明

### mcp_config.json中的LLM服务配置
```json
{
  "mcpServers": {
    "local-llm-agent": {
      "type": "stdio",
      "command": "python",
      "args": ["llm_agent.py"],
      "description": "MCP LLM Agent - 与本地大模型接口通信"
    }
  }
}
```

### llm_agent.py中的LLM API配置
```python
# 修改这些常量以适配您的LLM服务
LLM_BASE_URL = "http://localhost:12345"

LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions",      # 聊天接口
    "completion": "/v1/completions",     # 补全接口
    "generate": "/api/generate"          # 生成接口(Ollama)
}
```

### 简单测试

```python
# 创建 test_llm.py
import asyncio
from llm_agent import get_llm_client

async def test():
    client = get_llm_client()
    # 检查健康状态
    is_healthy = await client.health_check()
    print(f"LLM可用: {is_healthy}")
    
    if is_healthy:
        # 进行查询
        response = await client.chat([
            {"role": "user", "content": "Hello!"}
        ])
        print(f"响应: {response}")
    
    await client.close()

asyncio.run(test())


# 运行
python test_llm.py
```

---

## 💡 核心实现细节

### LLMClient如何工作

```python
# 1. 初始化
client = LLMClient(base_url="http://localhost:12345")

# 2. HTTP请求流程
async def chat(messages, temperature=0.7):
    session = await self._get_session()  # 创建aiohttp会话
    payload = {
        "model": "default",
        "messages": messages,
        "temperature": temperature
    }
    response = await session.post(  # 发送HTTP POST请求
        f"{base_url}/v1/chat/completions",
        json=payload,
        timeout=30
    )
    data = await response.json()  # 解析JSON响应
    return data['choices'][0]['message']['content']  # 提取文本

# 3. 返回结果
```

### MCP工具如何工作

```python
@mcp.tool()
async def ask_llm(question: str, chat_mode: str = "chat") -> dict:
    client = get_llm_client()  # 获取LLM客户端
    
    # 根据chat_mode选择接口
    if chat_mode == "chat":
        response = await client.chat([{"role": "user", "content": question}])
    
    # 返回结构化结果
    return {
        "success": True,
        "question": question,
        "response": response
    }
```

---

## 🎯 常见场景实现

### 场景1：问答系统

```python
# MCP客户端向ask_llm发送问题
{
  "name": "ask_llm",
  "arguments": {
    "question": "什么是递归算法？"
  }
}

# llm_agent.py处理流程：
# 1. 抽取question参数
# 2. 调用LLMClient.chat()
# 3. 向localhost:12345发送HTTP请求
# 4. 获取LLM回复
# 5. 返回结构化结果给MCP客户端
```

### 场景2：代码审查

```python
# MCP客户端请求代码审查
{
  "name": "ask_llm_with_context",
  "arguments": {
    "question": "这段代码有什么问题？",
    "context": "def slow_loop():\n    for i in range(1000000):\n        x = i * 2"
  }
}

# llm_agent.py处理：
# 1. 组织提示词：背景 + 问题
# 2. 调用LLMClient.chat()
# 3. LLM分析代码
# 4. 返回改进建议
```

### 场景3：指令链（需要多步操作）

```python
# MCP客户端发送复杂指令
"用户要求计算sqrt(16)并解释结果"

# llm_agent.py处理：
# 1. 调用llm_analyze_instruction分析指令
# 2. LLM识别需要：calculation + explanation
# 3. 建议调用calculator工具
# 4. 再次调用ask_llm进行解释
# 5. 返回完整结果
```

---

## 🧪 测试与验证

### 完整测试流程

```bash
# 1. 终端1: 启动本地LLM
ollama serve --addr 127.0.0.1:12345

# 2. 终端2: 启动MCP管道
python mcp_pipe.py

# 3. 终端3: 运行测试脚本
python examples.py

# 4. 观察日志输出
# ✓ 应该看到"Successfully connected to WebSocket server"
# ✓ 应该看到HTTP请求日志
# ✓ 应该看到LLM响应内容
```

### 健康检查

```python
# 快速验证LLM是否可用
import asyncio
from llm_agent import get_llm_client

async def check():
    client = get_llm_client()
    is_ok = await client.health_check()
    print("✓ LLM可用" if is_ok else "✗ LLM不可用")
    await client.close()

asyncio.run(check())
```

---

## ⚙️ 高级配置

### 支持多个LLM服务

```python
# 在llm_agent.py中修改
class LLMClientV2:
    def __init__(self, llm_type="ollama", custom_url=None):
        if llm_type == "ollama":
            self.base_url = "http://localhost:11434"
            self.endpoint = "/api/generate"
        elif llm_type == "openai_compatible":
            self.base_url = custom_url or "http://localhost:8000"
            self.endpoint = "/v1/chat/completions"
        # ...其他LLM服务
```

### 添加认证和密钥

```python
# 在llm_agent.py中
async def chat(self, messages, api_key=None):
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    async with session.post(
        url,
        json=payload,
        headers=headers
    ) as resp:
        # ...
```

### 自定义错误处理

```python
# 添加重试机制
async def chat_with_retry(self, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await self.chat(messages)
        except (ConnectionError, asyncio.TimeoutError):
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise
```

---

## 📊 架构总结

### 信息流

```
输入: MCP指令 (如: ask_llm 工具调用)
  ↓
[llm_agent.py] 提取参数
  ↓
[LLMClient] 构建HTTP请求
  ↓
[aiohttp] 异步發送请求到localhost:12345
  ↓
[本地LLM] 处理请求并返回响应
  ↓
[LLMClient] 解析响应
  ↓
[llm_agent.py] 构建结果对象
  ↓
[mcp_pipe.py] 通过WebSocket返回给客户端
  ↓
输出: structured result dict
```

### 关键组件功能

| 组件 | 功能 | 技术 |
|------|------|------|
| `mcp_pipe.py` | WebSocket <-> stdio 转换 | websockets库 |
| `llm_agent.py` | MCP工具定义和执行 | FastMCP框架 |
| `LLMClient` | HTTP客户端 | aiohttp异步库 |
| `localhost:12345` | 本地LLM推理 | Ollama/LM Studio等 |

---

## 🔍 故障排查

### 问题1：连接被拒绝

```
错误: Connection refused to 127.0.0.1:12345
```

**解决方案：**
```bash
# 确认LLM服务运行
netstat -ano | findstr 12345  # Windows
lsof -i :12345                # Linux/Mac

# 确认地址和端口
# 在llm_agent.py中验证 LLM_BASE_URL
```

### 问题2：超时

```
错误: Timeout waiting for LLM response
```

**解决方案：**
```python
# 增加超时时间
client = LLMClient(timeout=60)  # 而不是默认的30

# 或在llm_agent.py中修改全局超时
```

### 问题3：JSON解析错误

```
错误: Failed to parse JSON response
```

**解决方案：**
```python
# 检查LLM服务的响应格式
# 在llm_agent.py中的chat()方法中添加日志
logger.debug(f"Raw response: {await resp.text()}")

# 然后根据实际格式调整解析代码
```

---

## 📖 文件清单

| 文件 | 说明 | 新增/修改 |
|------|------|---------|
| `llm_agent.py` | LLM代理模块（主要实现） | ✨ 新增 |
| `LLM_AGENT_GUIDE.md` | 详细使用指南 | ✨ 新增 |
| `LOCAL_LLM_CONFIG.md` | 本地LLM配置大全 | ✨ 新增 |
| `examples.py` | 7个实际使用示例 | ✨ 新增 |
| `mcp_config.json` | MCP服务配置 | 📝 已更新 |
| `requirements.txt` | Python依赖 | 📝 已更新(+aiohttp) |
| `IMPLEMENTATION_GUIDE.md` | 本文档 | ✨ 新增 |

---

## ✅ 下一步

1. **立即开始**
   ```bash
   pip install -r requirements.txt
   python mcp_pipe.py
   ```

2. **选择本地LLM**
   - [Ollama](https://ollama.ai) (推荐)
   - [LM Studio](https://lmstudio.ai)
   - 其他...

3. **运行示例**
   ```bash
   python examples.py
   ```

4. **集成到您的应用**
   - 通过MCP客户端调用工具
   - 或直接导入`llm_agent`模块

5. **自定义扩展**
   - 修改LLM接口地址
   - 添加新的MCP工具
   - 实现特殊业务逻辑

---

## 🎓 学习资源

- [MCP官方文档](https://modelcontextprotocol.io/)
- [Ollama官方网站](https://ollama.ai)
- [LM Studio](https://lmstudio.ai)
- [FastMCP框架](https://github.com/jlopp/fastmcp)
- [aiohttp文档](https://docs.aiohttp.org/)

---

## 📞 获得帮助

如有问题，请：
1. 检查日志输出（启用DEBUG级别）
2. 验证localhost:12345的可访问性
3. 参考`LOCAL_LLM_CONFIG.md`的故障排查部分
4. 查看`examples.py`中的类似场景

---

**祝您使用愉快！** 🚀
