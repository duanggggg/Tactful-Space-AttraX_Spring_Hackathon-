# 本地LLM服务配置示例
# 根据您使用的LLM服务，选择相应的配置

# ============================================================================
# 方式1: 使用 Ollama (推荐)
# ============================================================================
# Ollama是一个轻量级本地LLM运行器，易于安装和使用
# 
# 安装: https://ollama.ai
# 启动服务: ollama serve
# 默认端口: http://localhost:11434 (但本示例使用12345)
#
# 配置步骤：
# 1. 安装Ollama
# 2. 运行: ollama pull mistral (或其他模型)
# 3. 启动Ollama代理到12345端口:
#    ollama serve --addr 127.0.0.1:12345
#
# 然后在llm_agent.py中配置：
"""
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "generate": "/api/generate"  # Ollama使用generate接口
}
"""

# ============================================================================
# 方式2: 使用 LM Studio
# ============================================================================
# LM Studio是一个GUI应用，提供本地LLM推理
#
# 安装: https://lmstudio.ai
# 启动后在设置中配置:
# - Server: http://127.0.0.1:1234 (或自定义端口12345)
# - 选择模型并加载
#
# LM Studio完全兼容OpenAI API，配置如下：
"""
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions"  # OpenAI兼容
}
"""

# ============================================================================
# 方式3: 使用 LocalAI
# ============================================================================
# LocalAI是一个开源的本地AI API服务器
#
# Docker启动:
# docker run -p 12345:8080 -v /path/to/models:/models \
#   localai/localai:latest --models-path=/models
#
# 配置：
"""
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions",
    "completion": "/v1/completions"
}
"""

# ============================================================================
# 方式4: 使用 OpenAI兼容的其他服务
# ============================================================================
# 如: llama.cpp, vLLM等
#
# 通常启动方式:
# python -m llama_cpp.server --host 0.0.0.0 --port 12345 \
#   --model /path/to/model.gguf
#
# 配置：
"""
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/v1/chat/completions"
}
"""

# ============================================================================
# 方式5: 使用 Text Generation WebUI (oobabooga)
# ============================================================================
# 
# 启动脚本: python server.py --listen 127.0.0.1 --listen-port 12345
#
# 配置：
"""
LLM_BASE_URL = "http://localhost:12345"
LLM_ENDPOINTS = {
    "chat": "/api/v1/chat/completions"  # 或根据实际调整
}
"""

# ============================================================================
# 快速测试脚本
# ============================================================================

# 将以下脚本保存为 test_llm.py 并运行:

"""
import asyncio
import aiohttp
import json

async def test_llm():
    base_url = "http://localhost:12345"
    
    # 测试1: Ollama风格
    print("测试Ollama API...")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "mistral",
                "prompt": "Hello, how are you?",
                "stream": False
            }
            async with session.post(f"{base_url}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ Ollama API可用")
                    print(f"响应: {data}")
                else:
                    print(f"✗ Ollama API返回: {resp.status}")
    except Exception as e:
        print(f"✗ Ollama API错误: {e}")
    
    # 测试2: OpenAI兼容风格
    print("\n测试OpenAI风格API...")
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "default",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
            async with session.post(f"{base_url}/v1/chat/completions", json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ OpenAI API可用")
                    print(f"响应: {data}")
                else:
                    print(f"✗ OpenAI API返回: {resp.status}")
    except Exception as e:
        print(f"✗ OpenAI API错误: {e}")
    
    # 测试3: Health check
    print("\n测试Health Check...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{base_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    print(f"✓ Health check成功")
                else:
                    print(f"✗ Health check返回: {resp.status}")
    except Exception as e:
        print(f"✗ Health check错误: {e}")

asyncio.run(test_llm())
"""

# ============================================================================
# 环境变量配置 (.env文件)
# ============================================================================

# 创建 .env 文件，内容如下:
"""
# LLM服务配置
LLM_BASE_URL=http://localhost:12345
LLM_MODEL=default
LLM_TIMEOUT=30

# 可选：API密钥
LLM_API_KEY=your_api_key_here

# 日志级别
LOG_LEVEL=INFO
"""

# ============================================================================
# mcp_config.json LLM服务配置
# ============================================================================

# 如果需要为LLM服务设置特殊环境变量:
"""
{
  "mcpServers": {
    "local-llm-agent": {
      "type": "stdio",
      "command": "python",
      "args": ["llm_agent.py"],
      "env": {
        "LLM_BASE_URL": "http://localhost:12345",
        "LLM_TIMEOUT": "60",
        "LOG_LEVEL": "DEBUG"
      }
    }
  }
}
"""

# ============================================================================
# 推荐配置 (最简单的本地设置)
# ============================================================================

# 1. 安装Ollama
# 2. 运行: ollama pull mistral
# 3. 在另一个终端配置端口转发或直接运行ollama serve
# 4. 运行MCP: python mcp_pipe.py
#
# 这样您可以通过MCP使用Mistral模型！

# ============================================================================
# 调试技巧
# ============================================================================

# 1. 启用详细日志
# - 修改llm_agent.py中的logging.basicConfig为DEBUG

# 2. 使用curl测试
"""
curl -X POST http://localhost:12345/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mistral",
    "prompt": "What is 2+2?",
    "stream": false
  }'
"""

# 3. 监控网络流量
# - 在llm_agent.py中添加日志记录所有请求/响应

# ============================================================================
