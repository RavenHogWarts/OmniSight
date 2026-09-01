// 轻量事件总线。只服务"跨模块的一次性通知"（按键动画、数据失效），
// 状态一律走 store——两条通道混用会让"现在到底谁是真相"变得不可回答。
const topics = new Map();

export function on(topic, handler) {
  if (!topics.has(topic)) topics.set(topic, new Set());
  topics.get(topic).add(handler);
  return () => off(topic, handler);
}

export function off(topic, handler) {
  topics.get(topic)?.delete(handler);
}

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
