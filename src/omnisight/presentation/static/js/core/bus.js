// 轻量事件总线。只服务"跨模块的一次性通知"（按键动画、数据失效），
// 状态一律走 store——两条通道混用会让"现在到底谁是真相"变得不可回答。
/** @type {Map<string, Set<(payload: any, topic: string) => void>>} */
const topics = new Map();

/**
 * @param {string} topic
 * @param {(payload: any, topic: string) => void} handler
 * @returns {() => void} 注销函数
 */
export function on(topic, handler) {
  let handlers = topics.get(topic);
  if (!handlers) {
    handlers = new Set();
    topics.set(topic, handlers);
  }
  handlers.add(handler);
  return () => off(topic, handler);
}

/**
 * @param {string} topic
 * @param {(payload: any, topic: string) => void} handler
 */
export function off(topic, handler) {
  topics.get(topic)?.delete(handler);
}

/**
 * @param {string} topic
 * @param {unknown} [payload]
 */
export function emit(topic, payload) {
  const handlers = topics.get(topic);
  if (!handlers) return;
  // 复制一份再遍历：处理器里注销自己是常见写法。
  for (const handler of [...handlers]) {
    try {
      handler(payload, topic);
    } catch (error) {
      console.error(`总线处理器失败：${topic}`, error);
    }
  }
}

export function clear() {
  topics.clear();
}
