// 集中状态 + 按切片订阅（07 文档 §4.1）。
//
// 三条规矩：
//   1. 派生数据不入 store（排序结果、百分比、色阶最大值都在渲染时算）。两份真相
//      不同步是最难查的一类 bug。
//   2. 无变化的写入不通知订阅者（shallowEqual 拦截）。
//   3. `capabilities` 只存布尔值，**不存 platform.id 用于分支**——它只在设置页
//      作为一行展示信息（07 文档 §10）。
//
// `State` 是这一层的对外契约。`data` 按 `DataMap` 索引，于是视图里
// `state.data.appsPeriod` 直接就是 `UsagePeriodResponse | undefined`——字段拼错在
// 类型检查时就红，不必等到界面上显示成空白。
//
// **React 侧不直接调 subscribe**，走 core/useStore.ts 的 hook（它用
// useSyncExternalStore 把这里的订阅接进 React 的调度）。这一层刻意不认识 React：
// 路由、SSE、取数编排都在 React 之外，让它依赖 React 就等于把那些也拖进渲染树
// （15 文档 §4.2）。
import type {
  Capabilities,
  Coverage,
  DataMap,
  DegradedNotice,
  LayoutResponse,
  LiveCounters,
  LiveForeground,
  PeriodMeta,
  RequestFailure,
  SettingsResponse,
  StatusResponse,
} from '../types/api.d.ts';

/** 周期选择。`date` 用于 day/week/month，`start`/`end` 用于自定义区间。 */
export interface PeriodState {
  range: string;
  date: string | null;
  start: string | null;
  end: string | null;
}

/** 后端配置的界面偏好。周起始日与默认周期是**后端配置**，前端不猜。 */
export interface Prefs {
  weekStartsOn: number;
  defaultRange: string;
  keyboardLayout: string;
  titlesRecorded: boolean;
}

/** 实时状态。`mode` 是 stream / polling / offline 三者之一。 */
export interface LiveState {
  connected: boolean;
  mode: string;
  currentApp: LiveForeground | null;
  counters: LiveCounters | null;
}

export interface State {
  route: string;
  period: PeriodState;
  metric: string;
  timelineView: string;
  scopeAppId: number | null;
  selectedAppId: number | null;
  selectedKeyId: string | null;
  theme: string;
  heat: string;
  prefs: Prefs;
  settings: SettingsResponse | null;
  status: StatusResponse | null;
  capabilities: Capabilities | null;
  degraded: DegradedNotice[];
  layout: LayoutResponse | null;
  periodMeta: PeriodMeta | null;
  coverage: Coverage | null;
  live: LiveState;
  data: Partial<DataMap>;
  loading: Partial<Record<keyof DataMap, boolean>>;
  errors: Partial<Record<keyof DataMap, RequestFailure | null>>;
}

/** 以 key 为单位的三个映射切片。它们的写入走 setEntry / dropEntries。 */
type BagSlice = 'data' | 'loading' | 'errors';

const state: State = {
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

type Listener = (value: unknown, slice: unknown) => void;
const listeners = new Map<string, Set<Listener>>();

export function getState(): Readonly<State> {
  return state;
}

export function get<K extends keyof State>(slice: K): State[K] {
  return state[slice];
}

/**
 * 写一个切片。对象切片按浅合并，其余整体替换。
 * @returns 是否真的变了（无变化不通知订阅者）
 */
export function setState<K extends keyof State>(
  slice: K,
  patch: Partial<State[K]> | State[K],
): boolean {
  const previous = state[slice];
  let next: unknown;
  if (Array.isArray(patch) || patch === null || typeof patch !== 'object') next = patch;
  else next = { ...(previous as Record<string, unknown>), ...(patch as Record<string, unknown>) };
  if (equal(previous, next)) return false;
  state[slice] = next as State[K];
  notify(slice);
  return true;
}

/**
 * 强制替换（用于 data/loading/errors 这类以 key 为单位的映射）。
 *
 * 写入侧刻意收得松（unknown）：精度要在**读取侧**——视图读 state.data.appsPeriod
 * 时必须是 UsagePeriodResponse | undefined。写入侧唯一的调用者是 core/loader.ts，
 * 它在那里做一次"JSON 到声明类型"的断言，而那次断言由契约测试兜着
 * （tests/integration/test_frontend_contract.py）。
 */
export function setEntry(slice: BagSlice, key: keyof DataMap, value: unknown): boolean {
  const bag = state[slice] as Record<string, unknown>;
  if (equal(bag[key as string], value)) return false;
  // State[BagSlice] 是三者的联合，而 state[slice] 的位置类型是它们的交叉——
  // 这里的值只可能属于当前 slice，用 never 断言一次，比给三个切片各写一份好。
  (state as unknown as Record<string, unknown>)[slice] = { ...bag, [key]: value };
  notify(slice);
  return true;
}

export function dropEntries(slice: BagSlice, predicate: (key: string) => boolean): boolean {
  const next: Record<string, unknown> = {};
  let changed = false;
  for (const [key, value] of Object.entries(state[slice])) {
    if (predicate(key)) changed = true;
    else next[key] = value;
  }
  if (!changed) return false;
  (state as unknown as Record<string, unknown>)[slice] = next;
  notify(slice);
  return true;
}

/** @returns 注销函数 */
export function subscribe<K extends keyof State>(
  slice: K,
  handler: (value: State[K], slice: K) => void,
): () => void {
  let handlers = listeners.get(slice);
  if (!handlers) {
    handlers = new Set();
    listeners.set(slice, handlers);
  }
  handlers.add(handler as Listener);
  return () => {
    handlers?.delete(handler as Listener);
  };
}

function notify(slice: keyof State): void {
  const handlers = listeners.get(slice);
  if (!handlers) return;
  for (const handler of [...handlers]) {
    try {
      (handler as (value: State[keyof State], slice: string) => void)(state[slice], slice);
    } catch (error) {
      console.error(`订阅者失败：${slice}`, error);
    }
  }
}

/** 浅比较。数据是"整块替换"的接口响应，深比较不划算（07 文档 §4.1）。 */
export function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || a === undefined || b === undefined) return false;
  if (typeof a !== 'object' || typeof b !== 'object') return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  const keysA = Object.keys(left);
  const keysB = Object.keys(right);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => left[key] === right[key]);
}
