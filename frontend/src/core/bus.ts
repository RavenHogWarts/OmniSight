// 轻量事件总线。只服务"跨模块的一次性通知"（按键动画、数据失效），
// 状态一律走 store——两条通道混用会让"现在到底谁是真相"变得不可回答。
//
// **React 化之后它反而更重要**：实时按键动画是 `bus.on('key:press') → classList.add`
// 直接打到 104 键里的一个节点，绕过一切状态与渲染（15 文档 §4.2 点明这一处会变差，
// 因此这里刻意保留原路径——每秒数次的按键不该触发 React 的调度）。
type Handler = (payload: never, topic: string) => void;

const topics = new Map<string, Set<Handler>>();

/** @returns 注销函数 */
export function on<T = unknown>(topic: string, handler: (payload: T, topic: string) => void): () => void {
  let handlers = topics.get(topic);
  if (!handlers) {
    handlers = new Set();
    topics.set(topic, handlers);
  }
  handlers.add(handler as Handler);
  return () => off(topic, handler as (payload: unknown, topic: string) => void);
}

export function off(topic: string, handler: (payload: never, topic: string) => void): void {
  topics.get(topic)?.delete(handler);
}

export function emit(topic: string, payload?: unknown): void {
  const handlers = topics.get(topic);
  if (!handlers) return;
  // 复制一份再遍历：处理器里注销自己是常见写法。
  for (const handler of [...handlers]) {
    try {
      (handler as (payload: unknown, topic: string) => void)(payload, topic);
    } catch (error) {
      console.error(`总线处理器失败：${topic}`, error);
    }
  }
}

export function clear(): void {
  topics.clear();
}
