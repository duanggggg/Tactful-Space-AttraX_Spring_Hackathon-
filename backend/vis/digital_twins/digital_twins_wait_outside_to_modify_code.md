# 目录外如需修改的审阅清单

当前版本已经可以作为一个独立子工程运行，不需要先改主项目目录。

如果后续要把它真正挂进当前“管道 OpenClaw”工程，请按下面方式审阅后再改。

## 1. 后端接入主 FastAPI

建议修改目标：

- `backend/main.py`

建议方法：

1. 将 `backend/vis/docs/digital_twins/mock_backend/app.py` 中的接口拆成 `APIRouter`。
2. 在主 FastAPI 中挂载到独立前缀，例如：
   - `/api/digital-twins/*`
   - 或继续保持 `/api/v1/*`，但必须避免和现有管道接口冲突。
3. 保留当前 mock backend 的事件流端点：
   - `GET /api/v1/events/stream`
4. 如果主服务已有全局 CORS，删除子工程里的重复配置。

## 2. 前端接入主 React 应用

建议修改目标：

- `frontend/src/*`

建议方法：

1. 新增一个独立页面路由，例如 `/digital-twins`。
2. 将 `backend/vis/docs/digital_twins/frontend/src/*` 中的：
   - `App.jsx`
   - `components/*`
   - `scene/*`
   - `store/useTwinStore.js`
   移入主前端的一个 `digitalTwins/` 模块。
3. 如果主前端坚持 TypeScript，则按以下顺序转换：
   - `api/client.js` -> `client.ts`
   - `useTwinStore.js` -> `useTwinStore.ts`
   - `*.jsx` -> `*.tsx`
4. 安装缺失依赖：
   - `three`
   - `@react-three/fiber`
   - `@react-three/drei`
   - `zustand`

## 3. OpenClaw skill 目录接入

建议修改目标：

- `backend/agent/skills/`
- 或你的 OpenClaw 实际 `backend/skills/`

建议方法：

1. 将 `backend/vis/docs/digital_twins/scripts/_shared/twin_http.py` 复制为共享 HTTP 工具。
2. 将以下脚本包装成正式 skill：
   - `get_state.py`
   - `device_command.py`
   - `scene_activate.py`
   - `telemetry_tail.py`
   - `publish_event.py`
3. 每个 skill 都只调用 HTTP，不直接依赖前端。
4. 统一环境变量：
   - `SUNROOM_TWIN_BASE_URL`
   - `SUNROOM_TWIN_API_KEY`

## 4. workspace template 切换

建议修改目标：

- 当前 OpenClaw workspace template 配置

建议方法：

1. 新建一个 `sunroom_openclaw` workspace template。
2. 让它默认携带：
   - digital twins 技能说明
   - 场景列表
   - 设备 taxonomy
   - Office UI 事件桥说明
3. 把原来面向管道调度的 prompt 约束，替换为：
   - 先读状态
   - 再下命令
   - 再回读验证
   - 必要时广播 Office UI 事件

## 5. Office UI 联动

建议修改目标：

- 未来的 `backend/vis/office_ui/*`
- 或主前端中的展示执行区组件

建议方法：

1. 复用当前桥接口：
   - `POST /api/v1/office-ui/events`
2. Office UI 只消费标准事件，不反向依赖 digital twins 前端内部状态。
3. 如果需要统一总线，可把：
   - digital twins 事件
   - Office UI 事件
   收敛到同一个 SSE/消息总线封装。

## 6. 真设备替换顺序

建议方法：

1. 保持前端和 skill 不动。
2. 只替换 `mock_backend` 里的设备执行逻辑。
3. 替换顺序严格保持：
   - mock adapter
   - vendor adapter
   - gateway aggregation

## 7. 当前最小可行路线

如果你希望尽量少动主工程，又尽快跑起来，建议顺序是：

1. 先独立启动 `backend/vis/docs/digital_twins/mock_backend`
2. 再独立启动 `backend/vis/docs/digital_twins/frontend`
3. 最后用 `backend/vis/docs/digital_twins/scripts` 模拟 OpenClaw skill 调用

这条路线不需要修改当前管道项目代码。
