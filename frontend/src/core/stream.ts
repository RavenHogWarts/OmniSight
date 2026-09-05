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
import { emit } from './bus.ts';
import { get as apiGet, invalidate, tokenParam } from './api.ts';
import { setState } from './store.ts';
import type { DegradedNotice, LiveCounters, LiveForeground, StatusResponse } from '../types/api.d.ts';

const POLL_INTERVAL_MS = 30_000;

let source: EventSource | null = null;
let pollTimer = 0;
let disabled = false;

export function connect(): void {
  if (source || disabled) return;
  const token = tokenParam();
  if (!token) return;
  source = new EventSource(`/api/v1/stream?token=${encodeURIComponent(token)}`);

  source.addEventListener('open', () => {
    stopPolling();
    setState('live', { connected: true, mode: 'stream' });
  });

  source.addEventListener('status', (event) => {
    const payload = parse<{ degraded?: DegradedNotice[]; capture?: unknown }>(event.data);
    if (!payload) return;
    setState('degraded', payload.degraded || []);
    emit('capture:status', payload.capture || null);
  });

  source.addEventListener('keypress', (event) => {
    const payload = parse<{ keys?: string[] }>(event.data);
    // 只有 key_id，没有时间戳、没有顺序（08 文档 §2）。动画消费它，别处不许存。
    if (payload?.keys?.length) emit('key:press', payload.keys);
  });

  source.addEventListener('foreground', (event) => {
    const payload = parse<LiveForeground>(event.data);
    if (payload) setState('live', { currentApp: payload });
  });

  source.addEventListener('counters', (event) => {
    const payload = parse<LiveCounters>(event.data);
    if (payload) setState('live', { counters: payload });
  });

  source.addEventListener('invalidate', (event) => {
    const payload = parse<Record<string, unknown>>(event.data);
    invalidate();
    emit('data:invalidated', payload || {});
  });

  // 配置落盘了（18 文档 批 2）。**推的是"变了"，不是新的配置**——与 invalidate 同一个
  // 口径：服务端不猜前端拿它做什么，前端自己决定要重读哪些偏好。设置页与仪表盘现在是两个
  // 标签页，少了这一条，在一边改「周起始日」另一边会一直按旧的切周，而且不报错。
  source.addEventListener('settings', () => {
    invalidate();
    emit('settings:changed', {});
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

function parse<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

export function close(): void {
  if (source) {
    source.close();
    source = null;
  }
}

/** 30 秒轮询兜底：只重新拉状态并让缓存失效，UI 只是少了实时动画。 */
export function startPolling(): void {
  if (pollTimer) return;
  setState('live', { connected: false, mode: 'polling' });
  pollTimer = window.setInterval(async () => {
    try {
      const status = (await apiGet('/status')) as StatusResponse;
      setState('status', status);
      setState('degraded', status.degraded || []);
      invalidate();
      emit('data:invalidated', { data_version: status.data_version });
      // 设置可能在**另一个标签页**里被改了（18 文档 批 2）。SSE 那条路有专门的 `settings`
      // 事件；这条路上没有推送，因此顺带说一声"重读偏好"——`/settings` 是一个几 KB 的本地
      // 响应，30 秒一次可以忽略，而"在设置页改了周起始日、仪表盘一直按旧的切周"是一种
      // 不报错的错。
      //
      // **这一声分不清变没变**（那正是它与 SSE 的 `settings` 帧的区别），因此订阅者那边
      // 按"读回来的设置与上一份一样吗"决定要不要重取（main.tsx:loadPrefs）。
      emit('settings:changed', {});
    } catch {
      // 轮询失败不弹提示：进程可能正在重启，下一轮会自己恢复。
    }
  }, POLL_INTERVAL_MS);
}

function stopPolling(): void {
  if (!pollTimer) return;
  window.clearInterval(pollTimer);
  pollTimer = 0;
}

export function stop(): void {
  close();
  stopPolling();
}
