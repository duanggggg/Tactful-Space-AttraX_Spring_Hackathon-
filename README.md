# HomeLLM

一个集成了AI代理、管道数据可视化、数字孪生和MCP协议的智能系统。结合了FastAPI后端、LLM编排和Model Context Protocol扩展能力。

## 📋 项目概述

**HomeLLM** 是一个综合性的AI驱动平台，主要用于天然气管道网络的可视化、调度和智能决策。系统包含两个核心部分：

1. **Backend** - 基于FastAPI的GIS管道后端系统
2. **MCP** - Model Context Protocol实现的AI能力扩展模块

### 核心特性

- 🤖 **AI代理编排** - 基于Trace的智能代理协调系统
- 📊 **管道数据可视化** - 实时天然气管道网络数据展示
- 🔄 **数字孪生支持** - 数字孪生虚实映射能力
- 🛠️ **技能系统** - 可扩展的技能管理（文档、PDF、幻灯片等）
- 🔌 **MCP集成** - Model Context Protocol协议支持
- 💾 **智能内存管理** - 会话记忆和知识图谱管理
- ⚙️ **灵活工具框架** - 工作区工具和自定义插件支持

## 📁 项目结构

```
homellm/
├── backend/                          # FastAPI后端系统
│   ├── main.py                      # 主应用入口
│   ├── agent/                       # AI代理核心模块
│   │   ├── orchestrator.py          # 代理编排引擎
│   │   ├── router.py                # 路由管理
│   │   ├── prompt_builder.py        # 提示词构建
│   │   ├── memory_manager.py        # 内存管理
│   │   ├── trace_writer.py          # 轨迹记录
│   │   ├── twin_bridge.py           # 数字孪生桥接
│   │   ├── services/                # 服务模块
│   │   │   ├── context_assembler.py # 上下文组装
│   │   │   └── memory_assembler.py  # 内存组装
│   │   ├── skills/                  # 技能系统
│   │   │   ├── bignum-calculator/   # 大数计算技能
│   │   │   ├── docx/                # Word文档处理
│   │   │   ├── pdf/                 # PDF处理
│   │   │   ├── pptx/                # PowerPoint处理
│   │   │   └── fluid-model/         # 流体模型
│   │   └── tools/                   # 工具系统
│   │       ├── registry.py          # 工具注册
│   │       └── workspace_tools.py   # 工作区工具
│   ├── executor/                    # 执行器模块
│   │   ├── runner.py                # 执行运行器
│   │   └── workspace_models.py      # 工作区数据模型
│   ├── pipeline_data/               # 管道数据
│   │   ├── node_flow/               # 节点流数据
│   │   ├── pipeline_flow/           # 管道流数据
│   │   └── consumer_flow/           # 消费者流数据
│   ├── vis/                         # 可视化模块
│   │   └── digital_twins/           # 数字孪生实现
│   │       ├── frontend/            # 前端应用
│   │       ├── mock_backend/        # 模拟后端
│   │       └── scripts/             # 启动脚本
│   ├── workspace-templates/         # 工作区模板
│   │   ├── AGENTS.md                # 代理配置
│   │   ├── MEMORY.md                # 内存配置
│   │   ├── TOOLS.md                 # 工具配置
│   │   └── memory/                  # 内存存储
│   ├── requirements.txt             # Python依赖
│   └── README.md                    # 后端文档
│
├── mcp/                             # Model Context Protocol模块
│   ├── mcp_pipe.py                  # MCP通信管道
│   ├── llm_agent.py                 # LLM代理实现
│   ├── calculator.py                # 计算器工具示例
│   ├── device_llm_server.py         # 设备LLM服务器
│   ├── mcp_config.json              # MCP配置文件
│   ├── requirements.txt             # MCP依赖
│   ├── QUICK_START_GUIDE.md         # 快速开始指南
│   └── README.md                    # MCP模块文档
│
├── start_all_services.sh            # Linux/Mac启动脚本
├── start_all_services.bat           # Windows启动脚本
├── start_all_services.ps1           # PowerShell启动脚本
└── README.md                        # 本文件
```

## 🚀 快速开始

### 前置要求

- Python 3.8+
- pip 或 conda
- Node.js 14+ (用于前端)

### 安装步骤

#### 1. 克隆项目
```bash
git clone https://github.com/yourusername/homellm.git
cd homellm
```

#### 2. 安装后端依赖
```bash
cd backend
pip install -r requirements.txt
```

#### 3. 配置环境变量
```bash
# 创建 .env 文件
cat > backend/.env << EOF
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.xiaomimimo.com/v1/chat/completions
OPENAI_MODEL=mimo-v2-pro
MAX_AGENT_STEPS=30
EOF
```

#### 4. 安装MCP依赖（可选）
```bash
cd mcp
pip install -r requirements.txt
```

### 运行系统

#### 方式一：启动所有服务（推荐）

**Linux/Mac:**
```bash
bash start_all_services.sh
```

**Windows (PowerShell):**
```powershell
.\start_all_services.ps1
```

**Windows (Cmd):**
```cmd
start_all_services.bat
```

#### 方式二：手动启动

**启动后端服务:**
```bash
cd backend
python main.py
# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

访问 API 文档：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

**启动MCP服务:**
```bash
cd mcp
python mcp_pipe.py
```

**启动数字孪生前端:**
```bash
cd backend/vis/digital_twins/frontend
npm install
npm start
```

## 📚 核心模块说明

### Backend 后端系统

#### 代理编排系统 (`agent/`)

- **orchestrator.py** - 核心编排引擎，管理代理的整个生命周期
- **router.py** - API路由，处理客户端请求
- **prompt_builder.py** - 动态构建LLM提示词
- **memory_manager.py** - 管理会话记忆和状态
- **trace_writer.py** - 记录代理执行轨迹用于调试和优化

#### 技能系统 (`agent/skills/`)

支持多种文档处理和计算能力：
- **bignum-calculator** - 大数值计算
- **docx** - Word文档处理
- **pdf** - PDF文件处理
- **pptx** - PowerPoint文件处理
- **fluid-model** - 流体动力学模型

#### 数据模块 (`pipeline_data/`)

管理天然气管道数据：
- `node_flow/` - 节点流量数据 (日期格式: YYYYMMDD_node.csv)
- `pipeline_flow/` - 管道流量数据 (日期格式: YYYYMMDD_pipeline.csv)
- `consumer_flow/` - 消费者流量数据
- `consumer_station.csv` - 供应点与站点映射

#### 数字孪生模块 (`vis/digital_twins/`)

前后端分离的数字孪生实现：
- **frontend/** - React/Vue前端应用
- **mock_backend/** - 模拟后端数据源
- **scripts/** - 启动和部署脚本

### MCP 模块

**Model Context Protocol** 实现，用于扩展AI能力：

- **mcp_pipe.py** - 主通信管道，处理WebSocket连接和进程管理
- **llm_agent.py** - LLM代理实现
- **calculator.py** - 示例工具实现
- **device_llm_server.py** - 设备级LLM服务器

支持的传输方式：
- `stdio` - 标准输入输出
- `sse` - Server-Sent Events
- `http` - HTTP协议

## 🔧 API 文档

### 后端 API 端点

#### 流量数据接口
```
GET /api/flow/nodes?query_date=YYYY-MM-DD
GET /api/flow/pipelines?query_date=YYYY-MM-DD  
GET /api/flow/consumers?query_date=YYYY-MM-DD
GET /api/flow/consumers/by-node?station_name=...&query_date=YYYY-MM-DD
```

#### 数据查询接口
```
GET /api/dates?data_type=node_flow|pipeline_flow|consumer_flow
GET /api/dates/range
```

#### 健康检查
```
GET /
```

### 代理交互接口

```
POST /agent/chat
{
  "user_input": "用户问题或命令",
  "session_id": "会话ID",
  "context": {...}
}
```

## 🛠️ 配置管理

### 环境变量 (backend/.env)

| 变量 | 说明 | 默认值 |
|-----|------|--------|
| `OPENAI_API_KEY` | OpenAI API密钥 | 必需 |
| `OPENAI_API_BASE` | API基础URL | https://api.xiaomimimo.com/v1/chat/completions |
| `OPENAI_MODEL` | 使用的模型 | mimo-v2-pro |
| `MAX_AGENT_STEPS` | 最大代理步数 | 30 |

### MCP配置 (mcp/mcp_config.json)

```json
{
  "mcpServers": {
    "server_name": {
      "type": "stdio|sse|http",
      "command": "...",
      "url": "...",
      "disabled": false
    }
  }
}
```

## 🧠 内存和知识管理

系统支持多层级的内存管理：

- **会话内存** - 单次对话的临时数据
- **用户内存** - 用户级别的长期知识
- **系统内存** - 全局共享的知识图谱
- **轨迹记录** - 代理执行的完整日志

存储位置: `backend/workspace-templates/memory/`

## 📖 文档

详细文档请查看各模块目录：

- [Backend详细文档](backend/README.md)
- [MCP详细文档](mcp/README.md)
- [快速开始指南](mcp/QUICK_START_GUIDE.md)
- [LLM代理指南](mcp/LLM_AGENT_GUIDE.md)
- [设备服务器指南](mcp/DEVICE_LLM_SERVER_GUIDE.md)
- [实现指南](mcp/IMPLEMENTATION_GUIDE.md)

## 🎯 使用场景

1. **天然气管道管理** - 实时监测和调度管道网络
2. **智能客服** - 利用AI代理处理用户咨询
3. **文档处理** - 自动化处理各类文档（Word、PDF、PPT等）
4. **数据分析** - 利用技能系统进行复杂数据计算
5. **数字孪生** - 构建虚实映射的数字孪生系统
6. **知识管理** - 智能知识库和内存管理

## 🔐 安全考虑

- API密钥通过环境变量管理，不提交到版本控制
- CORS配置支持跨域请求（生产环境需调整）
- MCP通信支持安全的WebSocket连接
- 所有用户输入需要验证和清理

## 🐛 调试和日志

系统会生成详细的日志文件：

- `backend.log` - 后端运行日志
- `backend/workspace-templates/context_trace/` - 代理执行轨迹
- `.run_logs/` - 运行时日志

启用调试模式：
```python
# 在 backend/main.py 中修改日志级别
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用多许可证模式：
- 代码部分：MIT License
- 文档部分：Creative Commons
- 第三方组件：参见各组件LICENSE文件

## 📞 联系方式

如有问题或建议，请：
1. 提交 Issue
2. 发起 Discussion
3. 联系开发者

## 🙏 致谢

感谢所有贡献者和使用者的支持！

---

**最后更新**: 2026年4月23日  
**项目状态**: 🚧 开发中
