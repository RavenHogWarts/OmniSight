// 集中状态 + 按切片订阅（07 文档 §4.1）。
//
// 三条规矩：
//   1. 派生数据不入 store（排序结果、百分比、色阶最大值都在渲染时算）。两份真相
//      不同步是最难查的一类 bug。
//   2. 无变化的写入不通知订阅者（shallowEqual 拦截）。
//   3. `capabilities` 只存布尔值，**不存 platform.id 用于分支**——它只在设置页
//      作为一行展示信息（07 文档 §10）。

const state = {
  route: 'overview',
  period: { range: 'day', date: null, start: null, end: null },
  metric: 'press_count',
  timelineView: 'hours',
  scopeAppId: null,
  selectedAppId: null,
  selectedKeyId: null,
  theme: 'system',
  heat: 'blue',
  // 由 GET /api/v1/settings 填充。周起始日与默认周期是**后端配置**，前端不猜。
  prefs: { weekStartsOn: 0, defaultRange: 'day', keyboardLayout: 'auto', titlesRecorded: false },
  settings: null,
  status: null,
  capabilities: null,
  degraded: [],
  layout: null,
  // 最近一次响应里的 period 段。周期栏的标题与箭头置灰都读它——**后端算好的区间**，
  // 前端不重算（07 文档 §10 第 3 行）。
  periodMeta: null,
  coverage: null,
  live: { connected: false, mode: 'offline', currentApp: null, counters: null },
  data: {},
  loading: {},
  errors: {},
};

const listeners = new Map();

export function getState() {
  return state;
}

export function get(slice) {
  return state[slice];
}

export function setState(slice, patch) {
  const previous = state[slice];
  let next;
  if (Array.isArray(patch) || patch === null || typeof patch !== 'object') next = patch;
  else next = { ...previous, ...patch };
  if (equal(previous, next)) return false;
  state[slice] = next;
  notify(slice);
  return true;
}

/** 强制替换（用于 data/loading/errors 这类以 key 为单位的映射）。 */
export function setEntry(slice, key, value) {
  const previous = state[slice][key];
  if (equal(previous, value)) return false;
  state[slice] = { ...state[slice], [key]: value };
  notify(slice);
  return true;
}

export function dropEntries(slice, predicate) {
  const next = {};
  let changed = false;
  for (const [key, value] of Object.entries(state[slice])) {
    if (predicate(key)) changed = true;
    else next[key] = value;
  }
  if (!changed) return false;
  state[slice] = next;
  notify(slice);
  return true;
}

export function subscribe(slice, handler) {
  if (!listeners.has(slice)) listeners.set(slice, new Set());
  listeners.get(slice).add(handler);
  return () => listeners.get(slice).delete(handler);
}

function notify(slice) {
  const handlers = listeners.get(slice);
  if (!handlers) return;
  for (const handler of [...handlers]) {
    try {
      handler(state[slice], slice);
    } catch (error) {
      console.error(`订阅者失败：${slice}`, error);
    }
  }
}

/** 浅比较。数据是"整块替换"的接口响应，深比较不划算（07 文档 §4.1）。 */
export function equal(a, b) {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => a[key] === b[key]);
}
