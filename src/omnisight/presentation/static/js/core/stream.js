// SSE 客户端（07 文档 §5.3）。
//
// 取代 KeyTrace 的本地 keydown 动画：那个只在浏览器窗口有焦点时有效，而用户看仪表盘时
// 焦点就在浏览器上，恰恰看不到自己在别的应用里打字的反馈。
//
// 服务端推的是"有新数据了"（invalidate），不是数据本身——它不猜前端在看哪个周期。
//
// 三种降级，行为都不同：
//   404  privacy.realtime_stream = false，用户主动关的。不重连，转 30 秒轮询。
//   错误  连接失败/断开。EventSource 自己重连，只更新指示灯。
//   无令牌 不连（EventSource 无法带请求头，令牌只能走查询串）。
import { emit } from './bus.js';
import { get as apiGet, invalidate, tokenParam } from './api.js';
import { setState } from './store.js';

const POLL_INTERVAL_MS = 30_000;

let source = null;
let pollTimer = 0;
let disabled = false;

export function connect() {
  if (source || disabled) return;
  const token = tokenParam();
  if (!token) return;
  source = new EventSource(`/api/v1/stream?token=${encodeURIComponent(token)}`);

  source.addEventListener('open', () => {
    stopPolling();
    setState('live', { connected: true, mode: 'stream' });
  });

  source.addEventListener('status', (event) => {
    const payload = parse(event.data);
    if (!payload) return;
    setState('degraded', payload.degraded || []);
    emit('capture:status', payload.capture || null);
  });

  source.addEventListener('keypress', (event) => {
    const payload = parse(event.data);
    // 只有 key_id，没有时间戳、没有顺序（08 文档 §2）。动画消费它，别处不许存。
    if (payload?.keys?.length) emit('key:press', payload.keys);
  });

  source.addEventListener('foreground', (event) => {
    const payload = parse(event.data);
    if (payload) setState('live', { currentApp: payload });
  });

  source.addEventListener('counters', (event) => {
    const payload = parse(event.data);
    if (payload) setState('live', { counters: payload });
  });

  source.addEventListener('invalidate', (event) => {
    const payload = parse(event.data);
    invalidate();
    emit('data:invalidated', payload || {});
  });

  source.addEventListener('bye', () => {
    // 服务端正在关闭：别让 EventSource 立刻重连去敲一个正在退出的进程。
    close();
    setState('live', { connected: false, mode: 'offline' });
  });

  source.addEventListener('error', () => {
    setState('live', { connected: false, mode: 'polling' });
    // readyState CLOSED 意味着不会自己重连了（多半是 404：流被用户关了）。
    if (source && source.readyState === EventSource.CLOSED) {
      close();
      disabled = true;
      startPolling();
    }
  });
}

function parse(data) {
  try {
    return JSON.parse(data);
  } catch (error) {
    return null;
  }
}

export function close() {
  if (source) {
    source.close();
    source = null;
  }
}

/** 30 秒轮询兜底：只重新拉状态并让缓存失效，UI 只是少了实时动画。 */
export function startPolling() {
  if (pollTimer) return;
  setState('live', { connected: false, mode: 'polling' });
  pollTimer = window.setInterval(async () => {
    try {
      const status = await apiGet('/status');
      setState('status', status);
      setState('degraded', status.degraded || []);
      invalidate();
      emit('data:invalidated', { data_version: status.data_version });
    } catch (error) {
      // 轮询失败不弹提示：进程可能正在重启，下一轮会自己恢复。
    }
  }, POLL_INTERVAL_MS);
}

function stopPolling() {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = 0;
}

export function stop() {
  close();
  stopPolling();
}
