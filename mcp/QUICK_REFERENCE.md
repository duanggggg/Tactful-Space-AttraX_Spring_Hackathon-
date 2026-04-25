# MCP + 本地LLM 快速参考卡

## 🎯 您的目标
获取MCP指令 → 转发给localhost:12345 → 返回结果

当前重点场景：
- 只要对话涉及房屋内电脑、灯光、空调功能，就进入 MCP + 本地/外部大模型链路
- 返回的不只是“识别到了哪个设备”，还包括每个家电要做什么，以及 digital twin 前后端联动结果

## ✅ 已完成
- ✓ 创建了`llm_agent.py` - 完整的LLM代理模块
- ✓ 更新了`mcp_config.json` - 添加LLM服务配置
- ✓ 更新了`requirements.txt` - 添加aiohttp依赖
- ✓ 创建了4份详细文档
- ✓ 提供了7个实际使用示例

## 🚀 3步启动

```bash
# 1. 安装依赖（第一次）
pip install -r requirements.txt

# 2. 启动本地LLM (终端1)
ollama serve --addr 127.0.0.1:12345

# 3. 启动MCP管道 (终端2)
python mcp_pipe.py
```

**就这么简单！** MCP客户端现在可以调用LLM工具了。

---

## 📋 可用工具

| 工具名称 | 用途 | 示例 |
|---------|------|------|
| `ask_llm` | 基础查询 | "解释回归分析" |
| `ask_llm_with_context` | 带背景info | "修复这个bug" + 代码 |
| `llm_code_completion` | 代码补全 | 补全函数实现 |
| `llm_analyze_instruction` | 分析指令 | 分解复杂任务 |

---

## 🔌 工作流程图

```
MCP客户端 
    ↓ 工具调用
mcp_pipe.py (管道)
    ↓ 转发
llm_agent.py (LLM代理)
    ↓ HTTP请求
LLMClient (异步客户端)
    ↓ POST到
localhost:12345 (本地LLM)
    ↓ 返回
MCP客户端 (最终结果)
```

---

## 💻 最小化代码示例

### 方式A: 通过MCP工具调用（推荐）

```json
{
  "name": "ask_llm",
  "arguments": {"question": "什么是MCP?"}
}
```

### 方式B: 直接Python代码调用

```python
import asyncio
from llm_agent import ask_llm

result = asyncio.run(ask_llm("什么是MCP?"))
print(result["response"])
```

### 方式C: 使用LLMClient类

```python
import asyncio
from llm_agent import LLMClient

async def main():
    client = LLMClient()
    response = await client.chat([{"role": "user", "content": "Hi!"}])
    print(response)
    await client.close()

asyncio.run(main())
```

---

## 🔧 关键配置

### llm_agent.py 中的设置

```python
# 修改这些参数以匹配您的LLM服务
LLM_BASE_URL = "http://localhost:12345"  # LLM地址

LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions",      # OpenAI兼容
    "completion": "/v1/completions",     # 文本补全
    "generate": "/api/generate"          # Ollama
}
```

---

## 📊 支持的LLM服务

| 服务 | 配置 | 说明 |
|------|------|------|
| **Ollama** | `/api/generate` | 推荐，最简单 |
| **LM Studio** | `/v1/chat/completions` | GUI应用 |
| **LocalAI** | `/v1/chat/completions` | Docker部署 |
| **LLaMA.cpp** | `/v1/chat/completions` | 命令行 |
| **Text Gen WebUI** | `/api/v1/chat` | 功能丰富 |

---

## 🧪 快速测试

### 测试脚本

```python
# test.py
import asyncio
from llm_agent import get_llm_client

async def test():
    client = get_llm_client()
    
    # 检查连接
    if not await client.health_check():
        print("❌ LLM服务不可用")
        return
    
    print("✓ LLM服务连接正常")
    
    # 发起查询
    response = await client.chat([
        {"role": "user", "content": "Hello!"}
    ])
    
    print(f"响应: {response}")
    await client.close()

asyncio.run(test())
```

**运行：** `python test.py`

---

## 📂 文件结构

```
项目目录/
├── llm_agent.py                    # ✨ LLM核心模块
├── mcp_config.json                 # MCP配置（已更新）
├── requirements.txt                # 依赖列表（已更新）
├── calculator.py                   # 计算器工具
├── mcp_pipe.py                     # MCP管道
│
├── 📖 文档
├── IMPLEMENTATION_GUIDE.md         # 完整实现指南
├── LLM_AGENT_GUIDE.md             # 使用详细说明
├── LOCAL_LLM_CONFIG.md            # LLM配置大全
├── QUICK_REFERENCE.md             # 本文件
│
├── 💡 示例
└── examples.py                     # 7个实际示例
```

---

## ⚡ 常用命令

```bash
# 启动所有MCP服务
python mcp_pipe.py

# 只启动LLM代理
python mcp_pipe.py local-llm-agent

# 只启动计算器
python mcp_pipe.py local-stdio-calculator

# 运行示例
python examples.py

# 测试LLM连接
python test.py
```

---

## 🐛 故障排查速查表

| 问题 | 原因 | 解决方案 |
|------|------|--------|
| `Connection refused` | LLM未运行 | `ollama serve --addr 127.0.0.1:12345` |
| `Timeout` | 响应太慢 | 增加超时: `timeout=60` |
| `JSON error` | 响应格式错误 | 检查`LLM_ENDPOINTS`配置 |
| `No module named xxx` | 缺少依赖 | `pip install -r requirements.txt` |

---

## 🔐 安全提示

1. **不要在代码中硬编码密钥**
   ```python
   # ❌ 错误
   api_key = "sk-1234567890"
   
   # ✅ 正确
   from os import getenv
   api_key = getenv("API_KEY")
   ```

2. **只信任本地连接**
   ```python
   # 限制只接受localhost连接
   LLM_BASE_URL = "http://127.0.0.1:12345"  # 而不是0.0.0.0
   ```

3. **添加请求验证**
   - 验证输入数据大小
   - 限制查询频率
   - 记录所有请求日志

---

## 💡 最佳实践

1. **始终检查health_check**
   ```python
   is_healthy = await client.health_check()
   if is_healthy:
       # 发起查询
   ```

2. **使用结构化错误处理**
   ```python
   result = await ask_llm("question")
   if result["success"]:
       print(result["response"])
   else:
       print(f"Error: {result['error']}")
   ```

3. **使用上下文信息**
   ```python
   await ask_llm_with_context(
       question="如何优化？",
       context="代码片段...",
       chat_mode="chat"
   )
   ```

4. **合理选择chat_mode**
   - `"chat"` → 对话和推理
   - `"completion"` → 代码补全
   - `"generate"` → 文本生成

---

## 📈 性能优化

- **批量请求：** 使用`asyncio.gather()`并发处理
- **连接复用：** `LLMClient`自动管理会话
- **合理超时：** 对于长查询增加超时时间
- **缓存结果：** 相同查询缓存LLM响应

---

## 🎓 学习路径

1. **新手入门**
   - 阅读本文件（快速参考）
   - 运行`examples.py`
   - 查看`LLM_AGENT_GUIDE.md`

2. **深入学习**
   - 研究`llm_agent.py`源代码
   - 阅读`IMPLEMENTATION_GUIDE.md`
   - 自定义LLM接口

3. **高级应用**
   - 多LLM支持
   - 请求缓存
   - 自定义工具

---

## 📞 快速查询

**Q: 如何修改LLM地址？**
A: 在`llm_agent.py`中改`LLM_BASE_URL`

**Q: 支持哪些LLM？**
A: 任何提供HTTP API的，详见`LOCAL_LLM_CONFIG.md`

**Q: 如何添加新工具？**
A: 在`llm_agent.py`中添加`@mcp.tool()`方法

**Q: 如何提高性能？**
A: 使用并发请求，参考`examples.py`中的示例5

**Q: 如何调试？**
A: 启用日志DEBUG级别，查看详细输出

---

## 🔗 资源链接

- [MCP官方文档](https://modelcontextprotocol.io/)
- [Ollama下载](https://ollama.ai)
- [LM Studio下载](https://lmstudio.ai)
- [FastMCP文档](https://github.com/jlopp/fastmcp)

---

## ✨ 总结

您现在拥有一个完整的MCP + 本地LLM集成系统：

✅ **MCP管道** - 接收并路由指令  
✅ **LLM代理** - 转发到本地大模型  
✅ **异步客户端** - 高效的HTTP通信  
✅ **工具集** - 多种查询方式  
✅ **文档** - 详细的使用说明  
✅ **示例** - 7个实际应用案例  

**现在就开始使用！** 🚀

---

最后更新：2026年4月1日
