# Device Taxonomy

## 一级域
- lighting
- access
- display
- environment
- sensing
- robot
- bridge

## 当前推荐设备 ID
- `light.perimeter`
- `light.entry`
- `screen.main`
- `door.main`
- `access.main`
- `window.north`
- `curtain.front`
- `ac.main`
- `freshair.main`
- `sensor.env`
- `sensor.occupancy`
- `sensor.rain`
- `robot.openclaw`

## 命名原则
- 使用稳定的英文小写 ID
- `domain.object` 两段式优先
- 状态字段尽量标准化
- 不把供应商品牌写进 device id

## 状态字段建议
### light
- `on`
- `brightness`
- `cct`
- `scene`

### door / window / curtain
- `position`
- `moving`
- `locked`（门）
- `auto_rule`

### screen
- `on`
- `mode`
- `message`

### ac / freshair
- `power`
- `mode`
- `setpoint`
- `fan_speed`
