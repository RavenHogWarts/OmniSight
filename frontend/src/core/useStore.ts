// store 与 React 之间的唯一胶水（15 文档 方案 A 批 4）。
//
// **为什么不用 zustand / Redux**：core/store.ts 已经是一个带切片订阅与 shallowEqual
// 拦截的 store，且 M3/M4 两轮实测过；useSyncExternalStore 正是为"外部 store 接进
// React 调度"设计的，接上它只要这十几行。换成 zustand 等于多一个运行时依赖 + 一次
// 重写，换来的是同一套语义。
//
// **为什么 store 不搬进 React**：路由（hash 与 store 的双向同步）、SSE、取数编排
// （AbortController）都在渲染树之外，而它们要读写同一份状态。把状态搬进 Context
// 之后，这三处就得靠"在某个组件里 useEffect"来驱动——那是把装配顺序藏进渲染时机里。
import { useSyncExternalStore } from 'react';
import { getState, subscribe } from './store.ts';
import type { State } from './store.ts';

/**
 * 订阅一个切片。切片没变就不重渲染——setState 里的 shallowEqual 已经拦住无变化写入，
 * 因此这里不需要再比一次。
 */
export function useSlice<K extends keyof State>(slice: K): State[K] {
  return useSyncExternalStore(
    (onChange) => subscribe(slice, onChange),
    () => getState()[slice],
  );
}

/**
 * 订阅多个切片，返回派生值。
 *
 * selector 必须**返回稳定的引用或原始值**——每次都新建对象会让 useSyncExternalStore
 * 认为状态一直在变（它按 Object.is 比较）。需要组合多个切片时，惯例是分别 useSlice
 * 再在组件体里组合，而不是在这里造对象。
 */
export function useSelector<T>(slices: readonly (keyof State)[], selector: (state: State) => T): T {
  return useSyncExternalStore(
    (onChange) => {
      const unsubscribes = slices.map((slice) => subscribe(slice, onChange));
      return () => unsubscribes.forEach((off) => off());
    },
    () => selector(getState()),
  );
}

/**
 * 取数状态：data / loading / errors 三个切片按同一个 key 索引。
 *
 * 这是视图里最常见的读法，收在这里免得每个视图各写三次 useSlice。
 */
export function useResource<K extends keyof State['data']>(
  key: K,
): { data: State['data'][K]; loading: boolean; error: State['errors'][K] } {
  const data = useSlice('data')[key];
  const loading = Boolean(useSlice('loading')[key]);
  const error = useSlice('errors')[key];
  return { data, loading, error };
}
