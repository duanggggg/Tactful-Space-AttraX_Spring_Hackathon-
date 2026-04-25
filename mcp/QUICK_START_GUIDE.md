# 🚀 MCP + 外部LLM 完整实现指南

## 📊 系统架构

```
【用户/MCP客户端】
     ↓ 只要涉及房屋内电脑/灯光/空调功能，就调用 classify_devices
【MCP层】llm_agent.py (stdio/WebSocket)
     ↓ POST http://localhost:12345/api/classify
【网关层】device_llm_server.py @ 12345端口
     ↓ POST http://127.0.0.1:48760/v1/chat/completions
【大模型层】gpt-5.4 (外部API)
     ↓
     返回设备识别结果 + 每个家电的执行方案
     ↓
【Digital Twin层】同步房屋内电脑/灯光/空调设备状态 + 3个 agent 状态
```

---

## ✅ 前置条件

- Python 3.8+
- 外部API已运行: `http://127.0.0.1:48760`
- 已配置API密钥: `fd65f6f696ae1a06db1a80764d4e7d8874e96f23b6abc9f07773540fb8b6baf4`

---

## 🎯 快速启动 (3步)

### 第1步: 安装依赖

```bash
pip install -r requirements.txt
```

依赖包括：
- fastapi >= 0.104.0
- uvicorn >= 0.24.0
- aiohttp >= 3.9.0
- fastmcp >= 2.13.0.2
- python-dotenv >= 1.2.1

### 第2步: 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env (应该已经包含正确的配置)
OPENAI_API_KEY=fd65f6f696ae1a06db1a80764d4e7d8874e96f23b6abc9f07773540fb8b6baf4
OPENAI_API_BASE=http://127.0.0.1:48760/v1/chat/completions
OPENAI_MODEL=gpt-5.4
```

### 第3步: 启动服务

**终端1: 启动网关服务**
```bash
python device_llm_server.py
```

预期输出:
```
============================================================
设备LLM服务启动配置
============================================================
✓ LLM API: http://127.0.0.1:48760/v1/chat/completions
✓ 模型: gpt-5.4
✓ 密钥: fd65f6f696ae1a...
============================================================
启动架构:
  MCP (llm_agent.py)
    ↓ POST http://localhost:12345/api/classify
  device_llm_server.py
    ↓ POST http://127.0.0.1:48760/v1/chat/completions
  外部大模型 (gpt-5.4)
============================================================
```

**终端2: 启动MCP**
```bash
python mcp_pipe.py
```

---

## 🧪 验证系统

### 方式1: 运行测试脚本

```bash
python test_device_server.py
```

它现在会同时检查：

- `device_llm_server` 自身是否启动
- LLM API 是否真的可达
- digital twin 是否真的可达
- 分类接口是否还能正确识别空调/灯光意图

预期输出:
```
【步骤1】健康检查
✓ 健康检查成功
  状态: ok
  端口: 12345
  模型API: http://127.0.0.1:48760/v1/chat/completions

【步骤2】功能测试
测试1: 只有空调
输入: 打开空调
预期: ['空调工作中']
✓ 通过 - 识别到: ['空调工作中']

...

🎉 所有测试通过！
```

### 方式2: 手动curl测试

```bash
# 测试分类
curl -X POST http://127.0.0.1:12345/api/classify \
  -H "Content-Type: application/json" \
  -d '{"input":"打开空调和灯"}'

# 预期响应
{
  "success": true,
  "devices": ["空调工作中", "灯光工作中"],
  "analysis": "用户要求打开空调和灯，涉及两个设备..."
}

# 健康检查
curl http://127.0.0.1:12345/health

# 深度健康检查
curl http://127.0.0.1:12345/health/deep
```

### 方式3: 通过MCP客户端调用

```python
# MCP客户端代码示例
result = await classify_devices("打开空调和灯")
print(result)
# 输出:
# {
#   "success": True,
#   "devices": ["空调工作中", "灯光工作中"],
#   "analysis": "..."
# }
```

---

## 📋 可用工具

MCP现在支持以下工具:

| 工具名 | 说明 | 示例 |
|-------|------|------|
| `ask_llm` | 基础LLM查询 | `ask_llm("解释MCP")` |
| `ask_llm_with_context` | 带上下文查询 | `ask_llm_with_context("修复bug", code)` |
| `llm_code_completion` | 代码补全 | `llm_code_completion("def foo():")` |
| `llm_analyze_instruction` | 指令分析 | `llm_analyze_instruction("同步数据")` |
| **`classify_devices`** | **🆕 设备分类** | **`classify_devices("打开空调")`** |

---

## 🔧 配置详解

### device_llm_server.py 配置

通过环境变量配置:

```bash
# 外部LLM API
OPENAI_API_KEY=你的API密钥
OPENAI_API_BASE=http://127.0.0.1:48760/v1/chat/completions
OPENAI_MODEL=gpt-5.4

# 监听端口
DEVICE_LLM_SERVER_PORT=12345
DEVICE_LLM_SERVER_HOST=127.0.0.1

# digital twin 同步
DIGITAL_TWIN_BASE_URL=http://127.0.0.1:8787
DIGITAL_TWIN_SYNC_ENABLED=true
```

### llm_agent.py 配置

MCP工具默认调用:
```python
# 网关地址（固定）
LLM_BASE_URL = "http://localhost:12345"

# 设备分类端点
POST /api/classify
```

---

## 🐛 故障排查

### 问题1: "无法连接到127.0.0.1:48760"

**原因**: 外部LLM API未运行

**解决**:
```bash
# 确保外部API正在运行
# 检查: http://127.0.0.1:48760 是否可以访问
curl http://127.0.0.1:48760/health
```

### 问题2: device_llm_server无法启动

**原因**: 端口12345被占用

**解决**:
```bash
# Windows
netstat -ano | findstr :12345
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :12345
kill -9 <PID>
```

### 问题3: MCP无法找到classify_devices工具

**原因**: llm_agent.py未正确加载

**解决**:
```bash
# 检查文件是否包含classify_devices函数
grep "classify_devices" llm_agent.py

# 重启MCP服务
# 终止当前运行，重新执行: python mcp_pipe.py
```

### 问题4: 识别结果不准确

这通常由以下原因引起:
1. 关键词不全 - 修改AC_KEYWORDS/LIGHT_KEYWORDS
2. 大模型配置错误 - 检查API密钥和模型名称
3. 网络问题 - 检查连接到外部API的网络

---

## 📊 系统流程图

```
用户输入
  ↓
MCP工具 (classify_devices)
  ↓
POST 请求 → http://localhost:12345/api/classify
  ↓
device_llm_server
  ├─ 关键词匹配 (快速, < 10ms)
  ├─ LLM分析 (如需要, 1-5s)
  │   └─ POST → http://127.0.0.1:48760/v1/chat/completions
  └─ 结果综合
  ↓
返回 JSON
  {
    "success": true,
    "devices": ["空调工作中", "灯光工作中"],
    "analysis": "..."
  }
  ↓
MCP返回给客户端
```

---

## 📈 性能指标

| 操作 | 时间 | 说明 |
|------|------|------|
| 健康检查 | < 100ms | TCP | 
| 关键词匹配 | < 10ms | 纯本地 |
| LLM分析 | 1-5秒 | 网络+ API |
| 完整流程 | 1.5-5.5秒 | 总耗时 |

---

## 🎓 架构优势

✨ **清晰分层**
- MCP: 工具定义和客户端接口
- 网关: 请求处理和逻辑编排
- LLM: 深度文本理解

✨ **灵活切换**
- 轻松更换外部LLM API
- 支持多种API格式
- 离线关键词匹配备选

✨ **可扩展性**
- 易于添加新设备类型
- 容易定制LLM提示词
- 支持批量请求

---

## 📚 完整命令参考

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
# 编辑 .env 填入API密钥

# 3. 启动网关
python device_llm_server.py

# 4. 启动MCP (新终端)
python mcp_pipe.py

# 5. 测试 (第3个终端)
python test_device_server.py

# 6. 查看API文档
# 访问: http://127.0.0.1:12345/docs
```

---

## 🎉 success标志

如果你看到:
```
✓ 健康检查成功
✓ 所有测试通过
✓ MCP工具可用
```

说明系统已就绪! 🚀

---

**版本**: v1.0.0  
**最后更新**: 2026年4月  
**作者**: MCP团队
