// Attrax 智能家居中枢 — Dashboard 覆盖层
// 独立模块，被 house-detail.html 加载；通过 window.AttraxDashboard 对外暴露。
// 负责：Agent 讨论/决策（主面板） + 环境传感器 + 能源 KPI + 设备状态卡。
//
// 数据来源：homekgmas 多 agent 后端（默认 http://127.0.0.1:8000）
//   - POST /api/v1/tasks/demo        → 触发多 agent 讨论 + 规划 + 执行（同步返回 OrchestrationResult）
//   - POST /api/v1/tasks/external    → 同 demo，但执行后会广播到 SSE（小智机器人走这条）
//   - GET  /api/v1/tasks/stream      → SSE：监听外部源（机器人）触发的讨论结果
//   - GET  /api/v1/tasks/context/current → 获取当前 HomeState（设备、传感器）
//   - GET  /health                   → 连通性探测
// 后端不可达时自动降级到内置 FALLBACK_SCENARIOS。
// 能源 KPI 后端无数据，保持本地模拟（已在 UI 标注 SIMULATED）。

const params = new URLSearchParams(location.search);
const API_BASE = (params.get('api') || 'http://127.0.0.1:8000').replace(/\/+$/, '');

const PALETTE = {
  text: 'rgba(206, 232, 255, 0.96)',
  textMuted: 'rgba(168, 198, 230, 0.72)',
  textDim: 'rgba(168, 198, 230, 0.48)',
  bg: 'rgba(10, 22, 42, 0.78)',
  bgSoft: 'rgba(14, 28, 52, 0.55)',
  bgCard: 'rgba(18, 34, 62, 0.82)',
  border: 'rgba(120, 196, 255, 0.28)',
  borderStrong: 'rgba(140, 216, 255, 0.55)',
  accent: '#6ebdff',
  accentStrong: '#9dd8ff',
  success: '#6fe4b5',
  warn: '#ffc16b',
  danger: '#ff7a8a',
  shadow: '0 0 22px rgba(80, 176, 255, 0.18), inset 0 0 18px rgba(120, 196, 255, 0.06)',
};

// 覆盖 homekgmas 的 8 个 domain + orchestrator + sensor
const AGENT_META = {
  orchestrator:    { name: 'Orchestrator',    short: 'ORC', color: '#9dd8ff', role: '中枢调度' },
  cooling_agent:   { name: 'Cooling Agent',   short: 'AC',  color: '#7fd4ff', role: '空调/制冷' },
  lighting_agent:  { name: 'Lighting Agent',  short: 'LT',  color: '#ffd98a', role: '照明' },
  cover_agent:     { name: 'Cover Agent',     short: 'CV',  color: '#c6a8ff', role: '窗帘/卷帘' },
  music_agent:     { name: 'Music Agent',     short: 'MS',  color: '#ff9cc2', role: '音乐/音响' },
  fan_agent:       { name: 'Fan Agent',       short: 'FN',  color: '#9ef0d4', role: '风扇' },
  lock_agent:      { name: 'Lock Agent',      short: 'LK',  color: '#ffb894', role: '门锁/安防' },
  switch_agent:    { name: 'Switch Agent',    short: 'SW',  color: '#ffd062', role: '开关' },
  appliance_agent: { name: 'Appliance Agent', short: 'AP',  color: '#b0e5ff', role: '家电' },
  sensor:          { name: 'Sensor',          short: 'SN',  color: '#6fe4b5', role: '环境感知' },
};

function resolveAgentMeta(name) {
  if (!name) return { name: '?', short: '?', color: PALETTE.accent, role: '' };
  return AGENT_META[name] || { name, short: name.slice(0, 3).toUpperCase(), color: PALETTE.accent, role: 'agent' };
}

// 快速指令（点击一键派单给后端）
const QUICK_TASKS = [
  { label: 'Evening relax', text: 'Make the living room comfortable for evening relaxation with soft warm lighting.' },
  { label: 'Movie mode',    text: 'Start movie mode: dim the lights, close the covers, and set a relaxing temperature.' },
  { label: 'Focus / Study', text: 'Set a quiet study environment with bright neutral light and no music.' },
  { label: 'Morning',       text: 'Morning wake up: open the covers, turn on bright lights, set a comfortable temperature.' },
];

// 后端不可达时的降级数据
const FALLBACK_SCENARIOS = [
  {
    user: 'Cool the room to 23 degrees',
    steps: [
      { kind: 'user', agent: null, text: 'Cool the room to 23 degrees' },
      { kind: 'thought', agent: 'orchestrator', text: 'Offline fallback · waking cooling + sensor agents.' },
      { kind: 'thought', agent: 'cooling_agent', text: 'Target 23°C · cool mode · auto fan. ETA ~12 min.' },
      { kind: 'decision', agent: 'orchestrator', text: 'Fallback decision: ac.target=23°C', tags: ['cooling', '23°C'] },
    ],
  },
  {
    user: 'Dim living room lights to 30%',
    steps: [
      { kind: 'user', agent: null, text: 'Dim living room lights to 30%' },
      { kind: 'thought', agent: 'orchestrator', text: 'Offline fallback · waking lighting + sensor.' },
      { kind: 'thought', agent: 'lighting_agent', text: 'brightness=30%, color temp 4000K, fade 600ms.' },
      { kind: 'decision', agent: 'orchestrator', text: 'Fallback decision: light.brightness=30%', tags: ['lighting', '30%'] },
    ],
  },
];

const INITIAL_STATE = {
  devices: {
    ac:      { power: true,  target: 26, mode: 'cool', fan: 'auto' },
    light:   { power: true,  brightness: 80, color_temp: 4000 },
    curtain: { position: 100 },
    switch:  { power: true,  load: 'TV + AV' },
  },
  sensors: {
    temperature: 26.4,
    humidity: 58,
    illuminance: 420,
    co2: 612,
    occupancy: true,
  },
  energy: {
    pvPower: 1.84,
    batterySoc: 72,
    batteryPower: -0.3,
    homeLoad: 1.12,
    gridExport: 0.42,
    todayYield: 9.8,
    todaySaved: 4.2,
  },
};

// ---------- 工具 ----------
const h = (tag, styles = {}, props = {}) => {
  const el = document.createElement(tag);
  Object.assign(el.style, styles);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'text') el.textContent = v;
    else if (k === 'html') el.innerHTML = v;
    else el[k] = v;
  }
  return el;
};

const fmt = {
  temp: (v) => `${(+v).toFixed(1)}°C`,
  pct:  (v) => `${Math.round(+v)}%`,
  kw:   (v) => `${v >= 0 ? '+' : ''}${(+v).toFixed(2)} kW`,
  lux:  (v) => `${Math.round(+v)} lx`,
  ppm:  (v) => `${Math.round(+v)} ppm`,
};

const sleep = (ms) => new Promise((res) => setTimeout(res, ms));

// 通用拖动 — handle 是拖拽把手（通常是卡片的标题栏），el 是被移动的容器
function makeDraggable(el, handle) {
  handle = handle || el;
  handle.style.cursor = 'move';
  handle.style.userSelect = 'none';
  handle.style.touchAction = 'none';
  let startX = 0, startY = 0, origL = 0, origT = 0, dragging = false;

  const onDown = (e) => {
    // 忽略交互控件上的按下事件，避免阻止点击/输入
    const t = e.target;
    if (t.closest && t.closest('button, input, select, textarea')) return;
    dragging = true;
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const cy = e.touches ? e.touches[0].clientY : e.clientY;
    startX = cx; startY = cy;
    const rect = el.getBoundingClientRect();
    // 固定到 left/top 坐标系；清除 right/bottom/transform（dat.gui 带 translateY(-50%) 会把位置偏移）
    // 用 setProperty('', 'important') 强制盖过 CSS 的 !important
    el.style.setProperty('left',      rect.left + 'px', 'important');
    el.style.setProperty('top',       rect.top  + 'px', 'important');
    el.style.setProperty('right',     'auto',           'important');
    el.style.setProperty('bottom',    'auto',           'important');
    el.style.setProperty('transform', 'none',           'important');
    origL = rect.left; origT = rect.top;
    el.style.transition = 'none';
    e.preventDefault();
  };

  const onMove = (e) => {
    if (!dragging) return;
    const cx = e.touches ? e.touches[0].clientX : e.clientX;
    const cy = e.touches ? e.touches[0].clientY : e.clientY;
    const dx = cx - startX;
    const dy = cy - startY;
    // 软性边界：至少露出 24px
    const w = el.offsetWidth;
    const maxL = window.innerWidth - 24;
    const maxT = window.innerHeight - 24;
    const minL = -(w - 24);
    const minT = 0;
    const nl = Math.max(minL, Math.min(maxL, origL + dx));
    const nt = Math.max(minT, Math.min(maxT, origT + dy));
    el.style.setProperty('left', nl + 'px', 'important');
    el.style.setProperty('top',  nt + 'px', 'important');
  };
  const onUp = () => { dragging = false; };

  handle.addEventListener('mousedown',  onDown);
  handle.addEventListener('touchstart', onDown, { passive: false });
  window.addEventListener('mousemove',  onMove);
  window.addEventListener('touchmove',  onMove, { passive: false });
  window.addEventListener('mouseup',    onUp);
  window.addEventListener('touchend',   onUp);
}

// 给 dat.gui 注入一条"拖动条" + 绑定拖拽；通过 MutationObserver 等 .dg.ac 出现
function attachGuiDrag() {
  const tryAttach = () => {
    const dgRoot = document.querySelector('.dg.ac');
    const main = dgRoot && dgRoot.querySelector('.dg.main');
    if (!main || main.dataset.dragReady === '1') return false;
    main.dataset.dragReady = '1';

    const bar = document.createElement('div');
    bar.textContent = '⋮⋮  Controls';
    Object.assign(bar.style, {
      display: 'flex', alignItems: 'center', gap: '8px',
      padding: '7px 14px',
      fontSize: '11px', fontFamily: '"Inter", "Segoe UI", sans-serif',
      letterSpacing: '0.22em', textTransform: 'uppercase', fontWeight: '600',
      color: 'rgba(157, 216, 255, 0.95)',
      background: 'linear-gradient(135deg, rgba(110, 189, 255, 0.18), rgba(157, 216, 255, 0.04))',
      borderBottom: '1px solid rgba(120, 196, 255, 0.22)',
      cursor: 'move', userSelect: 'none',
    });
    main.insertBefore(bar, main.firstChild);
    makeDraggable(dgRoot, bar);
    return true;
  };

  if (tryAttach()) return;
  const mo = new MutationObserver(() => {
    if (tryAttach()) mo.disconnect();
  });
  mo.observe(document.body, { childList: true, subtree: true });
  // 兜底：10 秒后停止观察
  setTimeout(() => mo.disconnect(), 10000);
}

// ---------- 组件构建 ----------
function buildRoot() {
  // HUD 模式：root 只做开关容器，不布局。每张卡自己 fixed 定位到屏幕四角，
  // 3D 场景透出来、不被遮挡。
  const root = h('div', {
    position: 'fixed', inset: '0', zIndex: '40',
    pointerEvents: 'none', display: 'none',
    color: PALETTE.text,
    fontFamily: '"Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
  });
  return { root };
}

function cardBase({ title, subtitle, accent = PALETTE.accent, extraHead } = {}) {
  const card = h('div', {
    background: PALETTE.bg, border: `1px solid ${PALETTE.border}`,
    borderRadius: '16px', boxShadow: PALETTE.shadow,
    backdropFilter: 'blur(14px)', webkitBackdropFilter: 'blur(14px)',
    padding: '18px 22px', pointerEvents: 'auto',
    display: 'flex', flexDirection: 'column', minHeight: '0',
  });
  if (title) {
    const head = h('div', { display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '14px' });
    const dot = h('span', {
      width: '12px', height: '12px', borderRadius: '50%',
      background: accent, boxShadow: `0 0 10px ${accent}`, flexShrink: '0',
    });
    const t = h('span', {
      fontSize: '20px', letterSpacing: '0.22em', textTransform: 'uppercase',
      color: PALETTE.text, fontWeight: '600',
    }, { text: title });
    head.append(dot, t);
    if (subtitle) {
      const s = h('span', { fontSize: '18px', color: PALETTE.textMuted, marginLeft: 'auto' }, { text: subtitle });
      head.append(s);
    }
    if (extraHead) head.append(extraHead);
    card.appendChild(head);
  }
  return card;
}

// ---------- 状态 pill ----------
function buildStatusPill() {
  const pill = h('span', {
    display: 'inline-flex', alignItems: 'center', gap: '10px',
    padding: '6px 14px', fontSize: '18px', letterSpacing: '0.18em',
    textTransform: 'uppercase', fontWeight: '600',
    borderRadius: '999px', marginLeft: 'auto',
    transition: 'all 0.25s ease',
  });
  const dot = h('span', { width: '10px', height: '10px', borderRadius: '50%' });
  const text = h('span', {}, { text: 'INIT' });
  pill.append(dot, text);
  const set = (state) => {
    const map = {
      live:    { c: PALETTE.success, bg: 'rgba(111,228,181,0.12)', t: 'LIVE',    border: 'rgba(111,228,181,0.45)' },
      busy:    { c: PALETTE.accent,  bg: 'rgba(110,189,255,0.14)', t: 'BUSY',    border: 'rgba(110,189,255,0.45)' },
      mock:    { c: PALETTE.warn,    bg: 'rgba(255,193,107,0.12)', t: 'MOCK',    border: 'rgba(255,193,107,0.45)' },
      offline: { c: PALETTE.danger,  bg: 'rgba(255,122,138,0.12)', t: 'OFFLINE', border: 'rgba(255,122,138,0.45)' },
      init:    { c: PALETTE.textDim, bg: 'rgba(168,198,230,0.08)', t: 'INIT',    border: 'rgba(168,198,230,0.25)' },
    };
    const v = map[state] || map.init;
    dot.style.background = v.c;
    dot.style.boxShadow  = `0 0 8px ${v.c}`;
    text.textContent = v.t;
    text.style.color = v.c;
    pill.style.background = v.bg;
    pill.style.border = `1px solid ${v.border}`;
  };
  set('init');
  return { pill, set };
}

// ---------- Agent Discussion 主面板 ----------
function buildAgentPanel(onSubmit) {
  const status = buildStatusPill();
  const card = cardBase({
    title: 'AGENTS',
    subtitle: API_BASE.replace(/^https?:\/\//, ''),
    accent: PALETTE.accentStrong,
    extraHead: status.pill,
  });
  // 左上 —— 字号变大后宽度也扩到 540
  Object.assign(card.style, {
    position: 'fixed',
    left: '16px',
    top: '80px',
    width: '540px',
    maxHeight: 'calc(100vh - 120px)',
    minHeight: '480px',
    padding: '18px 22px',
  });

  // 决策 banner
  const banner = h('div', {
    background: 'linear-gradient(135deg, rgba(110, 189, 255, 0.18), rgba(157, 216, 255, 0.06))',
    border: `1px solid ${PALETTE.borderStrong}`, borderRadius: '12px',
    padding: '14px 18px', marginBottom: '14px',
    display: 'flex', flexDirection: 'column', gap: '8px',
  });
  const bannerLabel = h('div', {
    fontSize: '19px', letterSpacing: '0.18em', textTransform: 'uppercase',
    color: PALETTE.accentStrong, display: 'flex', gap: '10px', alignItems: 'center',
  }, { text: 'DECISION' });
  const bannerMeta = h('span', { fontSize: '18px', color: PALETTE.textMuted, marginLeft: 'auto' });
  bannerLabel.appendChild(bannerMeta);
  const bannerText = h('div', { fontSize: '25px', color: PALETTE.text, lineHeight: '1.45' }, { text: '等待指令…' });
  const bannerTags = h('div', { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  banner.append(bannerLabel, bannerText, bannerTags);
  card.appendChild(banner);

  // agent 状态条 — 全名（头像保留缩写）
  const agentsRow = h('div', { display: 'flex', gap: '8px', marginBottom: '14px', flexWrap: 'wrap' });
  const agentChips = {};
  for (const [id, meta] of Object.entries(AGENT_META)) {
    const chip = h('div', {
      display: 'flex', alignItems: 'center', gap: '10px',
      padding: '8px 16px', borderRadius: '999px',
      background: 'rgba(20, 38, 68, 0.7)',
      border: `1px solid rgba(255,255,255,0.08)`,
      fontSize: '21px', color: PALETTE.textMuted,
      transition: 'all 0.25s ease',
    });
    const dot = h('span', { width: '10px', height: '10px', borderRadius: '50%', background: PALETTE.textDim });
    const nm = h('span', {}, { text: meta.name });
    chip.append(dot, nm);
    chip._dot = dot;
    chip.title = `${meta.name} · ${meta.role}`;
    agentsRow.appendChild(chip);
    agentChips[id] = chip;
  }
  card.appendChild(agentsRow);

  // 对话流
  const feedWrap = h('div', {
    flex: '1', minHeight: '320px', overflow: 'hidden',
    display: 'flex', flexDirection: 'column',
    border: `1px solid rgba(120, 196, 255, 0.12)`,
    borderRadius: '12px', background: 'rgba(6, 14, 28, 0.45)',
  });
  const feed = h('div', {
    flex: '1', minHeight: '0', overflowY: 'auto',
    padding: '16px 20px',
    display: 'flex', flexDirection: 'column', gap: '14px',
    scrollBehavior: 'smooth',
  });
  feedWrap.appendChild(feed);
  card.appendChild(feedWrap);

  // 底部输入 + 快速指令
  const inputBar = h('div', { display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '14px' });
  const quickRow = h('div', { display: 'flex', flexWrap: 'wrap', gap: '8px' });
  QUICK_TASKS.forEach((q) => {
    const btn = h('button', {
      padding: '10px 18px', fontSize: '21px', letterSpacing: '0.04em',
      borderRadius: '999px', cursor: 'pointer',
      background: 'rgba(30, 58, 98, 0.7)',
      border: '1px solid rgba(140, 216, 255, 0.28)',
      color: PALETTE.text,
    }, { type: 'button', text: q.label });
    btn.onclick = () => onSubmit(q.text);
    btn.onmouseenter = () => { btn.style.background = 'rgba(50, 88, 138, 0.85)'; };
    btn.onmouseleave = () => { btn.style.background = 'rgba(30, 58, 98, 0.7)'; };
    quickRow.appendChild(btn);
  });

  const inputRow = h('div', { display: 'flex', gap: '10px' });
  const input = h('input', {
    flex: '1', minWidth: '0', padding: '14px 18px', fontSize: '24px',
    background: 'rgba(6, 14, 28, 0.75)',
    border: `1px solid ${PALETTE.border}`,
    borderRadius: '10px', color: PALETTE.text, outline: 'none',
  }, { type: 'text', placeholder: 'task description, Enter to send…' });
  const sendBtn = h('button', {
    padding: '14px 22px', fontSize: '20px', letterSpacing: '0.12em',
    textTransform: 'uppercase', fontWeight: '600',
    borderRadius: '10px', cursor: 'pointer',
    background: 'rgba(110, 189, 255, 0.2)',
    border: '1px solid rgba(140, 216, 255, 0.45)',
    color: PALETTE.accentStrong,
  }, { type: 'button', text: 'Send' });
  const submit = () => {
    const v = input.value.trim();
    if (!v) return;
    input.value = '';
    onSubmit(v);
  };
  sendBtn.onclick = submit;
  input.onkeydown = (e) => { if (e.key === 'Enter') submit(); };
  inputRow.append(input, sendBtn);
  inputBar.append(quickRow, inputRow);
  card.appendChild(inputBar);

  return {
    card,
    banner: { text: bannerText, tags: bannerTags, meta: bannerMeta },
    feed, agentChips, status, input,
  };
}

function appendBubble(feed, step) {
  const isUser = step.kind === 'user';
  const isDecision = step.kind === 'decision';
  const isWarn = step.kind === 'warning';
  const isConcern = step.kind === 'concern';
  const meta = step.agent ? resolveAgentMeta(step.agent) : null;

  const row = h('div', {
    display: 'flex', gap: '12px', alignItems: 'flex-start',
    flexDirection: isUser ? 'row-reverse' : 'row',
  });

  const avatar = h('div', {
    width: '46px', height: '46px', borderRadius: '50%', flexShrink: '0',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontSize: '18px', fontWeight: '700', letterSpacing: '0.02em',
    background: isUser ? 'rgba(110, 189, 255, 0.25)' : 'rgba(20, 38, 68, 0.9)',
    border: `1px solid ${meta ? meta.color : PALETTE.borderStrong}`,
    color: meta ? meta.color : PALETTE.accentStrong,
  }, { text: isUser ? 'U' : (meta ? meta.short : '?') });

  const bubble = h('div', {
    maxWidth: '86%', padding: '12px 16px', borderRadius: '12px',
    fontSize: '23px', lineHeight: '1.5',
    background: isUser
      ? 'rgba(110, 189, 255, 0.18)'
      : isDecision
        ? 'linear-gradient(135deg, rgba(111, 228, 181, 0.18), rgba(111, 228, 181, 0.04))'
        : isWarn
          ? 'linear-gradient(135deg, rgba(255, 122, 138, 0.2), rgba(255, 122, 138, 0.04))'
          : isConcern
            ? 'linear-gradient(135deg, rgba(255, 193, 107, 0.16), rgba(255, 193, 107, 0.04))'
            : 'rgba(18, 34, 62, 0.88)',
    border: `1px solid ${
      isDecision ? 'rgba(111, 228, 181, 0.5)'
      : isWarn ? 'rgba(255, 122, 138, 0.5)'
      : isConcern ? 'rgba(255, 193, 107, 0.45)'
      : PALETTE.border}`,
    color: PALETTE.text,
  });

  if (!isUser && meta) {
    const label = h('div', {
      fontSize: '19px', letterSpacing: '0.08em', textTransform: 'uppercase',
      color: meta.color, marginBottom: '5px', fontWeight: '600',
    }, { text: meta.name });
    bubble.appendChild(label);
  }
  const body = h('div', {}, { text: step.text });
  bubble.appendChild(body);

  if (step.rationale && step.rationale.length) {
    const r = h('ul', {
      margin: '10px 0 0', padding: '0 0 0 24px',
      fontSize: '21px', color: PALETTE.textMuted, lineHeight: '1.55',
    });
    step.rationale.forEach((t) => { r.appendChild(h('li', {}, { text: t })); });
    bubble.appendChild(r);
  }
  if (step.actionTags && step.actionTags.length) {
    const tagBox = h('div', { display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '10px' });
    step.actionTags.forEach((t) => {
      tagBox.appendChild(h('span', {
        padding: '4px 14px', fontSize: '20px', letterSpacing: '0.06em',
        borderRadius: '999px', background: 'rgba(110, 189, 255, 0.14)',
        color: PALETTE.accentStrong, border: '1px solid rgba(140, 216, 255, 0.3)',
      }, { text: t }));
    });
    bubble.appendChild(tagBox);
  }

  row.append(avatar, bubble);
  feed.appendChild(row);

  while (feed.children.length > 80) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}

// ---------- 能源 KPI 卡（后端无数据，保持模拟） ----------
function buildEnergyCard() {
  const simTag = h('span', {
    padding: '4px 12px', fontSize: '16px', letterSpacing: '0.16em',
    borderRadius: '999px', background: 'rgba(255, 193, 107, 0.12)',
    color: PALETTE.warn, border: '1px solid rgba(255, 193, 107, 0.35)',
    marginLeft: 'auto',
  }, { text: 'SIM' });
  const card = cardBase({ title: 'Energy', accent: '#ffc16b', extraHead: simTag });
  // 右上
  Object.assign(card.style, {
    position: 'fixed',
    right: '16px',
    top: '80px',
    width: '440px',
    padding: '18px 22px',
  });

  const grid = h('div', { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' });
  const make = (label) => {
    const cell = h('div', {
      background: PALETTE.bgSoft, borderRadius: '10px', padding: '12px 16px',
      border: `1px solid rgba(255,255,255,0.04)`,
    });
    const lbl = h('div', { fontSize: '19px', letterSpacing: '0.14em', color: PALETTE.textMuted, textTransform: 'uppercase' }, { text: label });
    const val = h('div', { fontSize: '30px', fontWeight: '600', color: PALETTE.text, marginTop: '4px' }, { text: '—' });
    const u = h('span', { fontSize: '20px', color: PALETTE.textMuted, marginLeft: '6px', fontWeight: '400' }, { text: '' });
    val.appendChild(u);
    cell.append(lbl, val);
    return { cell, val };
  };
  const pv = make('PV'), battery = make('Batt'), load = make('Load'), grid2 = make('Grid');
  grid.append(pv.cell, battery.cell, load.cell, grid2.cell);
  card.appendChild(grid);

  const foot = h('div', {
    marginTop: '14px', display: 'flex', justifyContent: 'space-between',
    fontSize: '20px', color: PALETTE.textMuted,
  });
  const yieldEl = h('span', {}, { text: '+0.0 kWh' });
  const savedEl = h('span', {}, { text: 'CO₂ −0.0 kg' });
  foot.append(yieldEl, savedEl);
  card.appendChild(foot);

  return { card, pv: pv.val, battery: battery.val, load: load.val, grid: grid2.val, yieldEl, savedEl };
}

// ---------- 环境传感器卡 ----------
function buildSensorCard() {
  const card = cardBase({ title: 'Environment', accent: '#6fe4b5' });
  // 右侧，位于 Energy 卡下方（字号变大后整体下移）
  Object.assign(card.style, {
    position: 'fixed',
    right: '16px',
    top: '370px',
    width: '440px',
    padding: '18px 22px',
  });

  const row = h('div', { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' });
  const pill = (label) => {
    const p = h('div', {
      background: PALETTE.bgSoft, borderRadius: '10px', padding: '12px 16px',
      border: `1px solid rgba(255,255,255,0.05)`,
    });
    const lbl = h('div', { fontSize: '19px', letterSpacing: '0.14em', color: PALETTE.textMuted, textTransform: 'uppercase' }, { text: label });
    const val = h('div', { fontSize: '28px', fontWeight: '600', color: PALETTE.text, marginTop: '4px' }, { text: '—' });
    p.append(lbl, val);
    return { p, val };
  };
  const t = pill('Temp'), hum = pill('Humidity'), lux = pill('Light'), co2 = pill('CO₂'), occ = pill('Occupancy');
  // Occupancy 单独占满一行
  occ.p.style.gridColumn = '1 / span 2';
  row.append(t.p, hum.p, lux.p, co2.p, occ.p);
  card.appendChild(row);
  return { card, temp: t.val, humidity: hum.val, lux: lux.val, co2: co2.val, occupancy: occ.val };
}

// ---------- 设备状态卡 ----------
function buildDevicesCard() {
  const card = cardBase({ title: 'Devices', accent: '#c6a8ff' });
  // 右下
  Object.assign(card.style, {
    position: 'fixed',
    right: '16px',
    bottom: '110px',
    width: '440px',
    padding: '18px 22px',
  });

  const makeRow = (icon, name) => {
    const r = h('div', {
      display: 'flex', alignItems: 'center', gap: '14px',
      padding: '12px 16px', background: PALETTE.bgSoft,
      borderRadius: '10px', border: `1px solid rgba(255,255,255,0.05)`,
      marginBottom: '8px',
    });
    const ic = h('span', {
      width: '40px', height: '40px', borderRadius: '10px',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(110, 189, 255, 0.14)', fontSize: '22px',
      flexShrink: '0',
    }, { text: icon });
    const col = h('div', { flex: '1', minWidth: '0' });
    const nm = h('div', { fontSize: '19px', color: PALETTE.textMuted, letterSpacing: '0.14em', textTransform: 'uppercase' }, { text: name });
    const st = h('div', { fontSize: '22px', color: PALETTE.text, fontWeight: '500', marginTop: '4px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, { text: '—' });
    col.append(nm, st);
    const led = h('span', { width: '12px', height: '12px', borderRadius: '50%', background: PALETTE.textDim, flexShrink: '0' });
    r.append(ic, col, led);
    return { row: r, status: st, led };
  };
  const ac = makeRow('❄', 'Living AC');
  const light = makeRow('◉', 'Living Light');
  const curtain = makeRow('▤', 'Living Cover');
  const sw = makeRow('⏻', 'Main Switch');
  // 最后一行消除多余间距
  sw.row.style.marginBottom = '0';
  card.append(ac.row, light.row, curtain.row, sw.row);
  return { card, ac, light, curtain, sw };
}

// buildRightColumn 已废弃 — HUD 模式下每张卡各自 fixed 定位到屏幕角落。

// ---------- 渲染 ----------
function renderDevices(ui, state) {
  const on = (b) => b ? PALETTE.success : PALETTE.textDim;
  const d = state.devices;
  ui.devices.ac.status.textContent = d.ac.power
    ? `${d.ac.mode} · ${d.ac.target}°C · fan ${d.ac.fan}` : 'off';
  ui.devices.ac.led.style.background = on(d.ac.power);
  ui.devices.ac.led.style.boxShadow = d.ac.power ? `0 0 8px ${PALETTE.success}` : 'none';

  ui.devices.light.status.textContent = d.light.power
    ? `${Math.round(d.light.brightness)}% · ${d.light.color_temp}K` : 'off';
  ui.devices.light.led.style.background = on(d.light.power);
  ui.devices.light.led.style.boxShadow = d.light.power ? `0 0 8px ${PALETTE.success}` : 'none';

  ui.devices.curtain.status.textContent = `position ${Math.round(d.curtain.position)}%`;
  ui.devices.curtain.led.style.background = d.curtain.position > 0 ? PALETTE.accent : PALETTE.textDim;
  ui.devices.curtain.led.style.boxShadow = d.curtain.position > 0 ? `0 0 8px ${PALETTE.accent}` : 'none';

  ui.devices.sw.status.textContent = d.switch.power ? d.switch.load : 'off';
  ui.devices.sw.led.style.background = on(d.switch.power);
  ui.devices.sw.led.style.boxShadow = d.switch.power ? `0 0 8px ${PALETTE.success}` : 'none';
}

function renderSensors(ui, state) {
  ui.sensors.temp.textContent      = fmt.temp(state.sensors.temperature);
  ui.sensors.humidity.textContent  = fmt.pct(state.sensors.humidity);
  ui.sensors.lux.textContent       = fmt.lux(state.sensors.illuminance);
  ui.sensors.co2.textContent       = fmt.ppm(state.sensors.co2);
  ui.sensors.occupancy.textContent = state.sensors.occupancy ? 'Present' : 'Empty';
}

function renderEnergy(ui, state) {
  const e = state.energy;
  ui.energy.pv.firstChild.data      = e.pvPower.toFixed(2);
  ui.energy.pv.lastChild.textContent = ' kW';
  ui.energy.battery.firstChild.data  = `${e.batterySoc}`;
  ui.energy.battery.lastChild.textContent = `% · ${fmt.kw(e.batteryPower)}`;
  ui.energy.load.firstChild.data     = e.homeLoad.toFixed(2);
  ui.energy.load.lastChild.textContent = ' kW';
  ui.energy.grid.firstChild.data     = fmt.kw(e.gridExport);
  ui.energy.grid.lastChild.textContent = '';
  ui.energy.yieldEl.textContent      = `Today +${e.todayYield.toFixed(1)} kWh`;
  ui.energy.savedEl.textContent      = `CO₂ −${e.todaySaved.toFixed(1)} kg`;
}

function renderDecisionBanner(ui, { text, tags = [], meta = '' }) {
  ui.agent.banner.text.textContent = text;
  ui.agent.banner.meta.textContent = meta;
  ui.agent.banner.tags.innerHTML = '';
  tags.forEach((t) => {
    const chip = h('span', {
      padding: '2px 8px', fontSize: '10px', letterSpacing: '0.1em',
      borderRadius: '999px', background: 'rgba(111, 228, 181, 0.12)',
      color: '#a4f0cf', border: '1px solid rgba(111, 228, 181, 0.35)',
    }, { text: t });
    ui.agent.banner.tags.appendChild(chip);
  });
}

function pulseAgent(ui, agentId) {
  const chip = ui.agent.agentChips[agentId];
  if (!chip) return;
  const meta = resolveAgentMeta(agentId);
  chip._dot.style.background = meta.color;
  chip._dot.style.boxShadow = `0 0 8px ${meta.color}`;
  chip.style.background = `rgba(30, 58, 98, 0.85)`;
  chip.style.color = meta.color;
  chip.style.borderColor = meta.color;
  clearTimeout(chip._t);
  chip._t = setTimeout(() => {
    chip._dot.style.background = PALETTE.textDim;
    chip._dot.style.boxShadow = 'none';
    chip.style.background = 'rgba(20, 38, 68, 0.7)';
    chip.style.color = PALETTE.textMuted;
    chip.style.borderColor = 'rgba(255,255,255,0.08)';
  }, 2600);
}

// ---------- HomeState → state 映射 ----------
function mapHomeState(home, state) {
  if (!home) return;
  if (typeof home.room_temperature_c === 'number') state.sensors.temperature = home.room_temperature_c;
  if (typeof home.room_humidity_pct === 'number')  state.sensors.humidity    = home.room_humidity_pct;
  if (typeof home.ambient_light_level === 'number') {
    // ambient_light_level 约 0-100，粗略映射到 lux 风格 0-2000
    state.sensors.illuminance = Math.max(0, home.ambient_light_level * 20);
  }
  if (home.occupancy && typeof home.occupancy === 'object') {
    state.sensors.occupancy = Object.values(home.occupancy).some(Boolean);
  }

  const devs = home.devices || {};
  const first = (obj) => (obj && typeof obj === 'object') ? Object.values(obj)[0] : null;

  const ac = first(devs.air_conditioners);
  if (ac) {
    if ('power' in ac) state.devices.ac.power = !!ac.power;
    if (typeof ac.target_temperature === 'number') state.devices.ac.target = ac.target_temperature;
    if (ac.mode) state.devices.ac.mode = ac.mode;
    if (ac.fan_speed) state.devices.ac.fan = ac.fan_speed;
  }
  const light = first(devs.lights);
  if (light) {
    if ('power' in light) state.devices.light.power = !!light.power;
    if (typeof light.brightness === 'number') state.devices.light.brightness = light.brightness;
  }
  const cover = first(devs.covers);
  if (cover && typeof cover.position === 'number') state.devices.curtain.position = cover.position;
  const sw = first(devs.switches);
  if (sw) {
    if ('power' in sw) state.devices.switch.power = !!sw.power;
    if (sw.mode) state.devices.switch.load = String(sw.mode);
  }
}

// ---------- 后端客户端 ----------
class BackendClient {
  constructor(base) { this.base = base; }
  async _fetch(path, init, timeoutMs = 15000) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const r = await fetch(`${this.base}${path}`, { ...(init || {}), signal: ctl.signal });
      if (!r.ok) throw new Error(`HTTP ${r.status} on ${path}`);
      return r.json();
    } finally {
      clearTimeout(timer);
    }
  }
  health()        { return this._fetch('/health', {}, 4000); }
  fetchContext()  { return this._fetch('/api/v1/tasks/context/current', {}, 6000); }
  sendTask(description) {
    return this._fetch('/api/v1/tasks/demo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description, source: 'user' }),
    }, 60000);
  }
  fetchPresets() { return this._fetch('/api/v1/environment/presets', {}, 5000); }
  applyPreset(name) {
    return this._fetch('/api/v1/environment/preset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }, 5000);
  }
  applyOverride(payload) {
    return this._fetch('/api/v1/environment/override', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }, 5000);
  }
}

// 把 plan.selected_actions 渲染为决策标签
function actionsToTags(actions, limit = 4) {
  if (!Array.isArray(actions)) return [];
  return actions.slice(0, limit).map((a) => {
    const dev = a.device_id || a.device || 'dev';
    const attr = a.attribute || a.attr || '?';
    const val = a.value ?? a.target ?? '';
    return val !== '' ? `${dev}.${attr}=${val}` : `${dev}.${attr}`;
  });
}

function actionTagsInline(actions, limit = 3) {
  if (!Array.isArray(actions)) return [];
  return actions.slice(0, limit).map((a) => {
    const dev = (a.device_id || '').split('_').slice(-1)[0] || a.device_id || 'dev';
    const attr = a.attribute || '?';
    const val = a.value ?? '';
    return val !== '' ? `${dev}.${attr}=${val}` : `${dev}.${attr}`;
  });
}

// ---------- 核心：把 OrchestrationResult 渲染成气泡流 ----------
async function playOrchestrationResult(ui, state, result, originalText) {
  const feed = ui.agent.feed;

  // 1) 用户原话
  appendBubble(feed, { kind: 'user', agent: null, text: originalText });
  await sleep(400);

  // 2) orchestrator 唤醒说明
  const selected = result.selected_agents || [];
  const scores = result.wakeup_scores || {};
  if (selected.length) {
    const scoreTxt = selected.map((a) => `${resolveAgentMeta(a).short}:${scores[a] ?? '?'}`).join(' · ');
    appendBubble(feed, {
      kind: 'thought', agent: 'orchestrator',
      text: `Waking ${selected.length} agents — ${scoreTxt}`,
    });
    selected.forEach((a) => pulseAgent(ui, a));
    await sleep(900);
  }

  // 3) 按 agent_dialogue 顺序播气泡
  const dialogue = Array.isArray(result.agent_dialogue) ? result.agent_dialogue : [];
  for (const entry of dialogue) {
    const agent = entry.agent_name || 'orchestrator';
    const actionTags = actionTagsInline(entry.actions || []);
    const kind = entry.turn_type === 'validation' ? 'concern'
               : entry.turn_type === 'revision'   ? 'thought'
               : 'thought';
    appendBubble(feed, {
      kind,
      agent,
      text: entry.summary || `(round ${entry.round_index ?? '?'} · ${entry.turn_type || 'turn'})`,
      rationale: entry.rationale || [],
      actionTags,
    });
    pulseAgent(ui, agent);

    // 顺便把 concerns 单独渲染（如果有）
    if (Array.isArray(entry.concerns) && entry.concerns.length) {
      for (const c of entry.concerns) {
        appendBubble(feed, { kind: 'concern', agent, text: c });
      }
    }
    await sleep(1100);
  }

  // 4) conflicts（如果有）
  const conflicts = Array.isArray(result.conflicts) ? result.conflicts : [];
  for (const c of conflicts) {
    const txt = c.description || c.reason || c.summary || JSON.stringify(c);
    appendBubble(feed, { kind: 'warning', agent: 'orchestrator', text: `Conflict detected: ${txt}` });
    await sleep(900);
  }

  // 5) 最终决策
  const plan = result.plan || {};
  const selectedActions = plan.selected_actions || [];
  const consensus = plan.consensus_level || 'n/a';
  const confidence = typeof plan.decision_confidence === 'number'
    ? `${Math.round(plan.decision_confidence * 100)}%` : '—';
  const decisionText = (result.user_view && result.user_view.summary)
    || `Executed ${selectedActions.length} action(s) · consensus ${consensus}`;
  appendBubble(feed, {
    kind: 'decision', agent: 'orchestrator', text: decisionText,
    actionTags: actionsToTags(selectedActions),
  });
  renderDecisionBanner(ui, {
    text: decisionText,
    tags: actionsToTags(selectedActions),
    meta: `consensus: ${consensus} · confidence ${confidence} · status ${result.status || 'ok'}`,
  });

  // 6) 执行快照 → 更新设备/传感器卡
  const snap = result.execution && result.execution.state_snapshot;
  if (snap) {
    mapHomeState(snap, state);
    renderDevices(ui, state);
    renderSensors(ui, state);
  }
}

// ---------- Mock fallback 循环（仅后端不可达时启用） ----------
function createFallbackLoop(ui, state) {
  let idx = 0, stepIdx = 0, tStep = null, tTick = null;

  function nextStep() {
    const scn = FALLBACK_SCENARIOS[idx % FALLBACK_SCENARIOS.length];
    if (stepIdx >= scn.steps.length) {
      idx++; stepIdx = 0;
      tStep = setTimeout(nextStep, 3200);
      return;
    }
    const step = scn.steps[stepIdx++];
    appendBubble(ui.agent.feed, step);
    if (step.agent) pulseAgent(ui, step.agent);
    if (step.kind === 'decision') {
      renderDecisionBanner(ui, { text: step.text, tags: step.tags || [], meta: 'offline fallback' });
    }
    tStep = setTimeout(nextStep, step.kind === 'decision' ? 1800 : 1300);
  }

  function tick() {
    state.sensors.temperature += (Math.random() - 0.5) * 0.08;
    state.sensors.humidity    += (Math.random() - 0.5) * 0.3;
    state.sensors.humidity     = Math.max(30, Math.min(85, state.sensors.humidity));
    state.sensors.illuminance += (Math.random() - 0.5) * 20;
    state.sensors.illuminance  = Math.max(0, state.sensors.illuminance);
    state.sensors.co2         += (Math.random() - 0.5) * 8;
    state.sensors.co2          = Math.max(400, Math.min(1200, state.sensors.co2));

    state.energy.pvPower      = Math.max(0, state.energy.pvPower + (Math.random() - 0.5) * 0.08);
    state.energy.homeLoad     = Math.max(0.2, state.energy.homeLoad + (Math.random() - 0.5) * 0.06);
    state.energy.batteryPower = state.energy.pvPower - state.energy.homeLoad;
    state.energy.gridExport   = -state.energy.batteryPower * 0.4;
    state.energy.todayYield  += state.energy.pvPower / 3600;
    renderSensors(ui, state);
    renderEnergy(ui, state);
  }

  return {
    start() {
      if (!tStep) tStep = setTimeout(nextStep, 500);
      if (!tTick) tTick = setInterval(tick, 1000);
    },
    stop() {
      clearTimeout(tStep); tStep = null;
      clearInterval(tTick); tTick = null;
    },
  };
}

// 能源永远是 mock，即使后端在线也要让数字"活着"
function createEnergyTicker(ui, state) {
  let t = null;
  return {
    start() {
      if (t) return;
      t = setInterval(() => {
        state.energy.pvPower      = Math.max(0, state.energy.pvPower + (Math.random() - 0.5) * 0.08);
        state.energy.homeLoad     = Math.max(0.2, state.energy.homeLoad + (Math.random() - 0.5) * 0.06);
        state.energy.batteryPower = state.energy.pvPower - state.energy.homeLoad;
        state.energy.gridExport   = -state.energy.batteryPower * 0.4;
        state.energy.todayYield  += state.energy.pvPower / 3600;
        renderEnergy(ui, state);
      }, 1200);
    },
    stop() { clearInterval(t); t = null; },
  };
}

// ---------- 主入口 ----------
function mount() {
  const state = JSON.parse(JSON.stringify(INITIAL_STATE));
  const { root } = buildRoot();

  const client = new BackendClient(API_BASE);
  let busy = false;
  let contextTimer = null;
  let fallback = null;
  let connected = false;
  let eventSource = null;

  const submitTask = async (text) => {
    if (busy) {
      appendBubble(ui.agent.feed, { kind: 'concern', agent: 'orchestrator', text: 'Previous task still running, queue ignored.' });
      return;
    }
    if (!connected) {
      appendBubble(ui.agent.feed, { kind: 'warning', agent: 'orchestrator', text: 'Backend offline — running local fallback only.' });
      return;
    }
    busy = true;
    ui.agent.status.set('busy');
    try {
      const result = await client.sendTask(text);
      await playOrchestrationResult(ui, state, result, text);
      ui.agent.status.set('live');
    } catch (err) {
      appendBubble(ui.agent.feed, {
        kind: 'warning', agent: 'orchestrator',
        text: `Task failed: ${err && err.message ? err.message : err}`,
      });
      ui.agent.status.set('offline');
      connected = false;
      startFallback();
    } finally {
      busy = false;
    }
  };

  const agent = buildAgentPanel(submitTask);
  const energy = buildEnergyCard();
  const sensor = buildSensorCard();
  const devices = buildDevicesCard();

  // HUD 模式：每张卡各自 fixed 定位，直接挂到 root
  root.append(agent.card, energy.card, sensor.card, devices.card);
  document.body.appendChild(root);

  // 使每张卡可拖拽：在标题栏前插一个 grip 图标，把 header 作为拖拽 handle
  const enableDrag = (card) => {
    const head = card.firstChild;
    if (!head) return;
    const grip = h('span', {
      fontSize: '22px', color: 'rgba(168, 198, 230, 0.45)',
      letterSpacing: '-1px', marginRight: '6px', fontWeight: '700',
      flexShrink: '0',
    }, { text: '⋮⋮' });
    head.insertBefore(grip, head.firstChild);
    makeDraggable(card, head);
  };
  [agent.card, energy.card, sensor.card, devices.card].forEach(enableDrag);

  // dat.gui 也可拖拽（独立于 dashboard 显示状态）
  attachGuiDrag();

  const ui = {
    root,
    agent: { feed: agent.feed, banner: agent.banner, agentChips: agent.agentChips, status: agent.status, input: agent.input },
    energy, sensors: sensor,
    devices: { ac: devices.ac, light: devices.light, curtain: devices.curtain, sw: devices.sw },
  };

  renderDevices(ui, state);
  renderSensors(ui, state);
  renderEnergy(ui, state);

  const energyTicker = createEnergyTicker(ui, state);

  async function pollContext() {
    try {
      const ctx = await client.fetchContext();
      mapHomeState(ctx, state);
      renderDevices(ui, state);
      renderSensors(ui, state);
      if (!connected) {
        connected = true;
        ui.agent.status.set('live');
        stopFallback();
      }
    } catch (err) {
      if (connected) {
        connected = false;
        ui.agent.status.set('offline');
        appendBubble(ui.agent.feed, { kind: 'warning', agent: 'orchestrator', text: `Context poll failed: ${err.message || err}. Falling back to mock.` });
        startFallback();
      }
    }
  }

  function startContextPolling() {
    if (contextTimer) return;
    pollContext();
    contextTimer = setInterval(pollContext, 10000);
  }
  function stopContextPolling() {
    clearInterval(contextTimer); contextTimer = null;
  }

  function startFallback() {
    if (!fallback) fallback = createFallbackLoop(ui, state);
    fallback.start();
    ui.agent.status.set('mock');
  }
  function stopFallback() {
    if (fallback) fallback.stop();
  }

  // 外部源（小智机器人 / 其他 MCP 客户端）触发的讨论会通过 SSE 推到这里
  function startEventStream() {
    if (eventSource) return;
    const url = `${API_BASE}/api/v1/tasks/stream`;
    try {
      eventSource = new EventSource(url);
    } catch (err) {
      console.warn('[dashboard] EventSource init failed:', err);
      return;
    }
    eventSource.addEventListener('hello', () => {
      console.info('[dashboard] SSE connected');
    });
    eventSource.addEventListener('task_result', async (ev) => {
      let payload;
      try { payload = JSON.parse(ev.data); }
      catch (e) { console.warn('[dashboard] SSE bad payload', e); return; }
      const { description, source = 'external', result } = payload || {};
      if (!result || !description) return;
      // dashboard 自己提交的会走 sendTask 同步路径，已经播过气泡，这里跳过
      if (source === 'user') return;
      if (busy) {
        // 同步任务正在跑，先把外部任务排到末尾用文字提示，避免动画错位
        appendBubble(ui.agent.feed, {
          kind: 'concern', agent: 'orchestrator',
          text: `外部任务到达（${source}），等本地任务结束后再播放：${description}`,
        });
        return;
      }
      busy = true;
      ui.agent.status.set('busy');
      try {
        appendBubble(ui.agent.feed, {
          kind: 'thought', agent: 'orchestrator',
          text: `📡 来自 ${source} 的输入`,
        });
        await playOrchestrationResult(ui, state, result, description);
        ui.agent.status.set(connected ? 'live' : 'mock');
      } catch (err) {
        appendBubble(ui.agent.feed, {
          kind: 'warning', agent: 'orchestrator',
          text: `渲染外部任务失败: ${err && err.message ? err.message : err}`,
        });
      } finally {
        busy = false;
      }
    });
    eventSource.onerror = (err) => {
      // EventSource 自带重连，不做额外处理；只在第一次提示
      if (eventSource && eventSource.readyState === EventSource.CLOSED) {
        console.warn('[dashboard] SSE closed, will reconnect');
      }
    };
  }

  function stopEventStream() {
    if (eventSource) {
      try { eventSource.close(); } catch {}
      eventSource = null;
    }
  }

  async function connect() {
    try {
      await client.health();
      connected = true;
      ui.agent.status.set('live');
      appendBubble(ui.agent.feed, {
        kind: 'thought', agent: 'orchestrator',
        text: `Connected to homekgmas at ${API_BASE}. Awaiting instructions.`,
      });
      startContextPolling();
      startEventStream();
    } catch (err) {
      connected = false;
      appendBubble(ui.agent.feed, {
        kind: 'warning', agent: 'orchestrator',
        text: `Backend unreachable (${err.message || err}). Running in MOCK mode.`,
      });
      startFallback();
    }
  }

  const api = {
    show() {
      root.style.display = 'block';
      energyTicker.start();
      connect();
    },
    hide() {
      root.style.display = 'none';
      energyTicker.stop();
      stopContextPolling();
      stopFallback();
      stopEventStream();
    },
    toggle(v) { v ? api.show() : api.hide(); },
    submit: submitTask,
    reset() {
      ui.agent.feed.innerHTML = '';
      ui.agent.banner.text.textContent = '等待指令…';
      ui.agent.banner.tags.innerHTML = '';
      ui.agent.banner.meta.textContent = '';
    },
    // 环境预设/覆盖（无 UI，留给后续触发方式接入）
    fetchPresets: () => client.fetchPresets(),
    applyPreset: async (name) => {
      const r = await client.applyPreset(name);
      pollContext();
      return r;
    },
    applyOverride: async (payload) => {
      const r = await client.applyOverride(payload);
      pollContext();
      return r;
    },
  };

  window.AttraxDashboard = api;
  return api;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mount, { once: true });
} else {
  mount();
}
