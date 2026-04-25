import React from 'react';

const items = [
  ['lighting', '灯光 / 灯带'],
  ['display', '屏幕与内容'],
  ['access', '门禁 / 门状态'],
  ['environment', '窗 / 帘 / 自动规则'],
  ['climate', '空调 / 新风'],
  ['sensing', '环境 / 雨量 / 占用'],
  ['robot', 'OpenClaw 机器人']
];

export default function LegendPanel() {
  return (
    <div className="legend-strip">
      {items.map(([key, label]) => (
        <div className="legend-item" key={key}>
          <span className={`legend-dot ${key}`}></span>
          {label}
        </div>
      ))}
    </div>
  );
}
