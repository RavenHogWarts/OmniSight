// 取数层（07 文档 §5.1）。解决四个现状问题：请求乱序、重复请求、每秒轮询、304 未利用。
//
// 这一层的返回值刻意是 `unknown`——它拿到的就是一段未经校验的 JSON。类型在
// core/loader.ts 那一处进入：它按 `DataMap` 把响应归到声明的形状，而那份声明由契约
// 测试对着真实端点核对。**别在这里假装知道形状**。
//
// **React 化之后这一层原样保留**（15 文档 §4.2）：去重、ETag/304、写后整体失效这三样
// 现有实现已经达标且有测试；换成 TanStack Query 是"又一个依赖 + 又一次重写"，而收益
// 只是把同样的逻辑挪到别人的库里。
import { emit } from './bus.ts';
import type { ApiErrorBody } from '../types/api.d.ts';

export type Params = Record<string, string | number | boolean | null | undefined>;

const BASE = '/api/v1';
const TOKEN_HEADER = 'X-OmniSight-Token';
const TOKEN_KEY = 'omnisight.token';

interface CacheEntry {
  data: unknown;
  at: number;
  etag: string | null;
}

const inflight = new Map<string, Promise<unknown>>();
const cache = new Map<string, CacheEntry>();

let token = '';

export class ApiError extends Error {
  readonly code: string;
  readonly field: string | null;
  readonly status: number;

  /**
   * @param body 响应体里的 `error` 段
   */
  constructor(body: ApiErrorBody | null | undefined, status: number) {
    super(body?.message || `HTTP ${status}`);
    this.name = 'ApiError';
    this.code = body?.code || 'http_error';
    this.field = body?.field || null;
    this.status = status;
  }
}

/**
 * 令牌只经 URL 交接一次，随后存 sessionStorage 并从地址栏抹掉（08 文档 §3.2b）。
 * @param fromPage 模板注入的 data-token
 */
export function adoptToken(fromPage: string | null | undefined): string {
  if (fromPage) {
    token = fromPage;
    try {
      sessionStorage.setItem(TOKEN_KEY, fromPage);
    } catch {
      // 隐私模式下写不进去：本次会话的内存副本仍然可用。
    }
    history.replaceState(null, '', window.location.pathname + window.location.hash);
    return token;
  }
  try {
    token = sessionStorage.getItem(TOKEN_KEY) || '';
  } catch {
    token = '';
  }
  return token;
}

/**
 * 把 catch 到的东西说成人话。写操作失败后进 toast 的文案都经这里。
 *
 * 原先每个调用点各写一遍 `error.field ? ... : error.message`，而 `error` 在类型上
 * 是 `unknown`——非 ApiError 的抛出（网络层的 TypeError）会让 toast 显示
 * `undefined`。这里兜住那一种。
 */
export function messageOf(error: unknown, fallback = '操作失败'): string {
  if (error instanceof ApiError) {
    // field 由后端给（05 文档 §9），带上它比"操作失败"有用得多。
    return error.field ? `${error.field}：${error.message}` : error.message;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function hasToken(): boolean {
  return Boolean(token);
}

/** SSE 用得到：EventSource 无法设置请求头，只能把令牌放查询串。 */
export function tokenParam(): string {
  return token;
}

/** @param path `/api/v1` 之后的部分 */
export function buildUrl(path: string, params: Params = {}): string {
  const url = new URL(BASE + path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue;
    url.searchParams.set(key, String(value));
  }
  return url.pathname + url.search;
}

export interface GetOptions {
  signal?: AbortSignal;
  maxAge?: number;
}

/** @returns 未经校验的 JSON；204 与 abort 给 null */
export async function get(path: string, params: Params = {}, options: GetOptions = {}): Promise<unknown> {
  const { signal, maxAge = 0 } = options;
  const url = buildUrl(path, params);
  const cached = cache.get(url);
  if (cached && maxAge && Date.now() - cached.at < maxAge) return cached.data;
  const pending = inflight.get(url);
  if (pending) return pending;

  const headers: Record<string, string> = { [TOKEN_HEADER]: token };
  if (cached?.etag) headers['If-None-Match'] = cached.etag;

  const promise = fetch(url, { signal, headers, credentials: 'omit' })
    .then(async (response) => {
      if (response.status === 304 && cached) return cached.data;
      if (response.status === 204) return null;
      const body = (await response.json().catch(() => null)) as { error?: ApiErrorBody } | null;
      if (!response.ok) throw new ApiError(body?.error, response.status);
      cache.set(url, { data: body, at: Date.now(), etag: response.headers.get('ETag') });
      return body;
    })
    .finally(() => inflight.delete(url));

  inflight.set(url, promise);
  return promise;
}

async function write(method: 'PATCH' | 'POST' | 'DELETE', path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(buildUrl(path), {
    method,
    credentials: 'omit',
    headers: { [TOKEN_HEADER]: token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => null)) as { error?: ApiErrorBody } | null;
  if (!response.ok) throw new ApiError(payload?.error, response.status);
  // 写操作会改变数据：清掉整个读缓存，别猜哪些 key 受影响。
  invalidate();
  emit('data:changed', { path });
  return payload;
}

export const patch = (path: string, body?: unknown) => write('PATCH', path, body);
export const post = (path: string, body?: unknown) => write('POST', path, body);
export const del = (path: string, body?: unknown) => write('DELETE', path, body);

/**
 * 清缓存。传前缀只清匹配的（周期变化时不必丢弃布局与设置）。
 */
export function invalidate(prefix = ''): void {
  if (!prefix) {
    cache.clear();
    return;
  }
  for (const key of [...cache.keys()]) {
    if (key.startsWith(BASE + prefix)) cache.delete(key);
  }
}

/**
 * 图标 URL 后端已给（`icon_url`），这里只补令牌——<img> 发不出自定义头。
 */
export function assetUrl(path: string | null | undefined): string {
  if (!path) return '';
  const separator = path.includes('?') ? '&' : '?';
  return `${path}${separator}token=${encodeURIComponent(token)}`;
}

export const BASE_PATH = BASE;
