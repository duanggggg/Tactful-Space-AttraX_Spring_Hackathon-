# Screen-Display · 智能家居路演大屏前端

阳光房路演用的**大屏展示前端**，基于 Three.js 的纯静态 Web 应用。
负责把 3D 房屋模型、Agent 讨论面板、设备状态卡和能源 KPI 渲染到大屏上。

> 这是 [`Agents.md`](../Agents.md) 里指定的"前端展示核心"，
> 视频脚本见 [`Attrax_competition/demo_script.md`](../Attrax_competition/demo_script.md)。

## 目录结构

```
screen-display/
├── screen-display/             # 静态前端（HTML/JS/GLB/纹理）
│   ├── index.html              # 入口：Smart City Interface（多页导航）
│   ├── house-detail.html       # 主展示：3D 阳光房 + Agent 讨论 + 设备
│   ├── house-isolate.html      # 单房间隔离视图
│   ├── exploded-diagram.html   # 爆炸图
│   ├── energy-tracking.html    # 能源追踪页
│   ├── house-detail.js         # 核心 Three.js 场景脚本
│   ├── dashboard-panel.js      # 大屏覆盖层：Agent 讨论 + KPI + 设备卡
│   ├── app.js                  # 通用工具
│   ├── layout.json             # 物体位置/姿态持久化数据（由 server 写入）
│   ├── models/ 、 *.glb         # 3D 资源
│   └── assets/ 、 textures-*    # 贴图与素材
└── server/
    ├── save_layout.py          # FastAPI：layout 持久化（:8788）
    └── run.sh                  # 用 backend/.venv 启 uvicorn
```

## 一键启动

> 默认使用项目根目录已有的 `backend/.venv` 作为 Python 环境。如果没有，先到 `backend/` 跑 `uv venv && uv pip install -r requirements.txt`。

打开两个终端：

**1. 启 layout 保存服务（:8788）**
```bash
cd screen-display/server
bash run.sh
# Windows PowerShell 直接：python -m uvicorn save_layout:app --host 127.0.0.1 --port 8788 --reload
```

**2. 启静态文件服务（:8080）**
```bash
cd screen-display/screen-display
python -m http.server 8080
```

然后浏览器打开：

- **主展示**：http://127.0.0.1:8080/house-detail.html
- 入口导航：http://127.0.0.1:8080/index.html
- 其他页：`house-isolate.html` / `exploded-diagram.html` / `energy-tracking.html`

> ⚠️ 必须通过 HTTP 打开，**不能 file:// 直接拖**——Three.js / Draco 远程依赖会被浏览器 CORS 拒绝。

## 端口与依赖关系

| 服务 | 端口 | 来源 | 作用 |
|------|------|------|------|
| 静态前端 | **:8080** | `python -m http.server 8080` | 提供 HTML/JS/GLB |
| Layout 保存 API | **:8788** | `screen-display/server/save_layout.py` | 加载/写入 `layout.json`（设备摆放位置） |
| 多 Agent 后端 | **:8000** | `homekgmas/scripts/run_server.py` | Agent 讨论 + 决策 + 执行（dashboard 数据源） |
| Mock 数字孪生 | **:8787** | `backend/vis/digital_twins/mock_backend/app.py` | 设备/场景状态（可选，备用展示通道） |

只想看 3D 静态展示，启 :8080 + :8788 就够了；
要演示**多智能体讨论**，必须再起 `homekgmas` 的 :8000。

## 关键页面说明

### `house-detail.html`（主舞台）
路演时大屏唯一展示的页面。包含：

- **3D 阳光房**：可拖拽视角，加载 `layout.json` 里保存的家具位置
- **Agent 讨论面板**（dashboard-panel.js 注入）：
  - 实时拉 `homekgmas` 的 `POST /api/v1/tasks/demo` / `external` 触发讨论
  - 通过 `GET /api/v1/tasks/stream` SSE 监听小机器人触发的外部任务
- **环境传感器卡** + **能源 KPI**（KPI 暂时是 SIMULATED 模拟数据）
- **设备状态卡**：空调 / 灯 / 屏幕 等

### `dashboard-panel.js` 配置
通过 URL query 切 API 地址：

```
http://127.0.0.1:8080/house-detail.html?api=http://127.0.0.1:8000
```

不传 `?api=` 时默认 `http://127.0.0.1:8000`。

后端不可达时会自动降级到内置 `FALLBACK_SCENARIOS`，UI 会标注 **OFFLINE / SIMULATED**，路演现场断网也能演示。

### Agent 元数据（dashboard-panel.js 内置）
覆盖 `homekgmas` 的 8 个 domain agent + orchestrator + sensor：

| Agent | 角色 | 颜色 |
|-------|------|------|
| `orchestrator` | 中枢调度 | `#9dd8ff` |
| `cooling_agent` | 空调/制冷 | `#7fd4ff` |
| `lighting_agent` | 照明 | `#ffd98a` |
| `cover_agent` | 窗帘/卷帘 | `#c6a8ff` |
| `music_agent` | 音乐/音响 | `#ff9cc2` |
| `fan_agent` | 风扇 | `#9ef0d4` |
| `lock_agent` | 门锁/安防 | `#ffb894` |
| `switch_agent` | 开关 | `#ffd062` |
| `appliance_agent` | 家电 | `#b0e5ff` |
| `sensor` | 环境感知 | `#6fe4b5` |

## 编辑布局（拖拽家具后保存）

`house-detail.html` 里有内嵌的家具拖拽工具（`dat.gui` 控件）：

1. 拖动家具到合适位置
2. 触发"保存"动作 → `POST :8788/api/save-layout`
3. `server/save_layout.py` 把 `transforms` 写入 `layout.json`，
   并把上一版备份到 `.layout_backups/layout.<timestamp>.json`（最多保留 10 份）

下次刷新页面时会从 `:8788/api/layout` 预加载，状态不会丢。

## 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 白屏 + 控制台 CORS 错误 | 用 `file://` 打开了 | 改成 `http://127.0.0.1:8080/...` |
| Agent 面板一直显示 `OFFLINE` | `homekgmas` 没起或端口被占 | `cd homekgmas && python -m scripts.run_server` |
| Layout 不保存 / 刷新就回原位 | `:8788` 没起 | 起 `server/run.sh`；或检查 `layout.json` 写权限 |
| 页面卡在加载 GLB | 网络拉 Three.js / Draco CDN 失败 | 换网或本地化依赖（见 `house-detail.js` 顶部 import） |
| 端口冲突 `WinError 10013` | 端口已被占用 | 换端口或先关掉旧进程 |

## 路演快速核对清单

- [ ] `:8080` 静态前端 200
- [ ] `:8788` `/api/health` 返回 `{"ok":true}`
- [ ] `:8000` `homekgmas` `/health` 200
- [ ] 浏览器打开 `house-detail.html`，3D 模型正常渲染
- [ ] 触发一次 `?api=` 测试 demo 任务，agent 讨论面板能滚出文本
- [ ] 大屏分辨率 1080p，浏览器 F11 全屏，关掉书签栏
