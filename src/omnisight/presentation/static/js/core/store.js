// 集中状态 + 按切片订阅（07 文档 §4.1）。
//
// 三条规矩：
//   1. 派生数据不入 store（排序结果、百分比、色阶最大值都在渲染时算）。两份真相
//      不同步是最难查的一类 bug。
//   2. 无变化的写入不通知订阅者（shallowEqual 拦截）。
//   3. `capabilities` 只存布尔值，**不存 platform.id 用于分支**——它只在设置页
//      作为一行展示信息（07 文档 §10）。
//
// 类型（07 文档 §2.1）：`State` 是这一层的对外契约。`data` 按 `DataMap` 索引，于是
// 视图里 `state.data.appsPeriod` 直接就是 `UsagePeriodResponse | undefined`——
// 字段拼错在类型检查时就红，不必等到界面上显示成空白。

/**
 * @typedef {import('../types/api.js').DataMap} DataMap
 * @typedef {import('../types/api.js').RequestFailure} RequestFailure
 */

/**
 * 周期选择。`date` 用于 day/week/month，`start`/`end` 用于自定义区间。
 * @typedef {object} PeriodState
 * @property {string} range
 * @property {string | null} date
 * @property {string | null} start
 * @property {string | null} end
 */

/**
 * 后端配置的界面偏好。周起始日与默认周期是**后端配置**，前端不猜。
 * @typedef {object} Prefs
 * @property {number} weekStartsOn
 * @property {string} defaultRange
 * @property {string} keyboardLayout
 * @property {boolean} titlesRecorded
 */

/**
 * 实时状态。`mode` 是 stream / polling / offline 三者之一。
 * @typedef {object} LiveState
 * @property {boolean} connected
 * @property {string} mode
 * @property {import('../types/api.js').LiveForeground | null} currentApp
 * @property {import('../types/api.js').LiveCounters | null} counters
 */

/**
 * @typedef {object} State
 * @property {string} route
 * @property {PeriodState} period
 * @property {string} metric
 * @property {string} timelineView
 * @property {number | null} scopeAppId
 * @property {number | null} selectedAppId
 * @property {string | null} selectedKeyId
 * @property {string} theme
 * @property {string} heat
 * @property {Prefs} prefs
 * @property {import('../types/api.js').SettingsResponse | null} settings
 * @property {import('../types/api.js').StatusResponse | null} status
 * @property {import('../types/api.js').Capabilities | null} capabilities
 * @property {import('../types/api.js').DegradedNotice[]} degraded
 * @property {import('../types/api.js').LayoutResponse | null} layout
 * @property {import('../types/api.js').PeriodMeta | null} periodMeta
 * @property {import('../types/api.js').Coverage | null} coverage
 * @property {LiveState} live
 * @property {Partial<DataMap>} data
 * @property {Partial<Record<keyof DataMap, boolean>>} loading
 * @property {Partial<Record<keyof DataMap, RequestFailure | null>>} errors
 */

/** @type {State} */
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

/** @type {Map<string, Set<(value: any, slice: any) => void>>} */
const listeners = new Map();

/** @returns {Readonly<State>} */
export function getState() {
  return state;
}

/**
 * @template {keyof State} K
 * @param {K} slice
 * @returns {State[K]}
 */
export function get(slice) {
  return state[slice];
}

/**
 * 写一个切片。对象切片按浅合并，其余整体替换。
 * @template {keyof State} K
 * @param {K} slice
 * @param {Partial<State[K]> | State[K]} patch
 * @returns {boolean} 是否真的变了（无变化不通知订阅者）
 */
export function setState(slice, patch) {
  const previous = state[slice];
  let next;
  if (Array.isArray(patch) || patch === null || typeof patch !== 'object') next = patch;
  // 两处断言只是告诉 TS"到这一行 patch 必是对象"——泛型切片下它推不出来。
  else {
    next = {
      ...(/** @type {Record<string, unknown>} */ (previous)),
      ...(/** @type {Record<string, unknown>} */ (patch)),
    };
  }
  if (equal(previous, next)) return false;
  state[slice] = /** @type {State[K]} */ (next);
  notify(slice);
  return true;
}

/**
 * 强制替换（用于 data/loading/errors 这类以 key 为单位的映射）。
 *
 * 写入侧刻意收得松（`unknown`）：精度要在**读取侧**——视图读 `state.data.appsPeriod`
 * 时必须是 `UsagePeriodResponse | undefined`。写入侧唯一的调用者是 core/loader.js，
 * 它在那里做一次"JSON → 声明的类型"的断言，而那次断言由契约测试兜着
 * （tests/integration/test_frontend_contract.py）。
 * @param {'data' | 'loading' | 'errors'} slice
 * @param {keyof DataMap} key
 * @param {unknown} value
 * @returns {boolean}
 */
export function setEntry(slice, key, value) {
  const bag = /** @type {Record<string, unknown>} */ (state[slice]);
  if (equal(bag[key], value)) return false;
  state[slice] = /** @type {State['data'] & State['loading'] & State['errors']} */ ({
    ...bag,
    [key]: value,
  });
  notify(slice);
  return true;
}

/**
 * @param {'data' | 'loading' | 'errors'} slice
 * @param {(key: string) => boolean} predicate
 * @returns {boolean}
 */
export function dropEntries(slice, predicate) {
  /** @type {Record<string, unknown>} */
  const next = {};
  let changed = false;
  for (const [key, value] of Object.entries(state[slice])) {
    if (predicate(key)) changed = true;
    else next[key] = value;
  }
  if (!changed) return false;
  state[slice] = /** @type {State['data'] & State['loading'] & State['errors']} */ (next);
  notify(slice);
  return true;
}

/**
 * @template {keyof State} K
 * @param {K} slice
 * @param {(value: State[K], slice: K) => void} handler
 * @returns {() => void} 注销函数
 */
export function subscribe(slice, handler) {
  let handlers = listeners.get(slice);
  if (!handlers) {
    handlers = new Set();
    listeners.set(slice, handlers);
  }
  handlers.add(handler);
  return () => handlers.delete(handler);
}

/** @param {keyof State} slice */
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

/**
 * 浅比较。数据是"整块替换"的接口响应，深比较不划算（07 文档 §4.1）。
 * @param {unknown} a
 * @param {unknown} b
 * @returns {boolean}
 */
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
