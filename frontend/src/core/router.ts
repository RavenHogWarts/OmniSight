// hash 路由与 URL 同步（07 文档 §4.2）。
//
// 两种历史行为，刻意不同：
//   - 换视图用 pushState —— 用户期望返回键回到上一个页面。
//   - 换周期/指标用 replaceState —— 否则连点 20 次日期箭头后要按 20 次返回键。
//
// **刻意不用 react-router**：路由在这里只是"store 的一个切片 ↔ 地址栏"的双向同步，
// 上面那两种历史行为是它的全部业务。react-router 会把这层搬进渲染树，于是"周期变了
// 要不要产生历史条目"变成它的配置问题，而那是本项目里真正需要精确控制的一处。
import { getState, setState, subscribe } from './store.ts';

export const ROUTES = ['overview', 'apps', 'keyboard', 'insights'] as const;
export type Route = (typeof ROUTES)[number];

const DEFAULT_ROUTE: Route = 'overview';

let applying = false;

function isRoute(value: string): value is Route {
  return (ROUTES as readonly string[]).includes(value);
}

/** `#/keyboard?range=week&date=2026-08-31&metric=duration_avg_ms` */
export function parseHash(hash: string = window.location.hash): {
  route: Route;
  params: URLSearchParams;
} {
  const raw = String(hash || '').replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const route = isRoute(path) ? path : DEFAULT_ROUTE;
  return { route, params: new URLSearchParams(query) };
}

export function currentQuery(): URLSearchParams {
  const { period, metric, scopeAppId, selectedAppId } = getState();
  const params = new URLSearchParams();
  params.set('range', period.range);
  if (period.range === 'custom') {
    if (period.start) params.set('start', period.start);
    if (period.end) params.set('end', period.end);
  } else if (period.date) {
    params.set('date', period.date);
  }
  if (metric !== 'press_count') params.set('metric', metric);
  if (scopeAppId) params.set('scope', String(scopeAppId));
  if (selectedAppId) params.set('app', String(selectedAppId));
  return params;
}

function hashFor(route: string): string {
  const query = currentQuery().toString();
  return `#/${route}${query ? `?${query}` : ''}`;
}

/** URL -> store。用户手改地址、前进后退都走这里。 */
export function applyFromHash(): void {
  const { route, params } = parseHash();
  applying = true;
  try {
    setState('period', {
      range: params.get('range') || 'day',
      date: params.get('date') || null,
      start: params.get('start') || null,
      end: params.get('end') || null,
    });
    setState('metric', params.get('metric') || 'press_count');
    setState('scopeAppId', toId(params.get('scope')));
    setState('selectedAppId', toId(params.get('app')));
    setState('route', route);
  } finally {
    applying = false;
  }
}

function toId(value: string | null): number | null {
  const id = Number.parseInt(value ?? '', 10);
  return Number.isInteger(id) && id > 0 ? id : null;
}

export function go(route: string): void {
  if (!isRoute(route) || getState().route === route) return;
  history.pushState(null, '', hashFor(route));
  setState('route', route);
}

/** store -> URL，静默。视图切换之外的一切状态变化都用它。 */
function syncHash(): void {
  if (applying) return;
  const next = hashFor(getState().route);
  if (next !== window.location.hash) history.replaceState(null, '', next);
}

export function start(): void {
  window.addEventListener('hashchange', applyFromHash);
  window.addEventListener('popstate', applyFromHash);
  const slices = ['period', 'metric', 'scopeAppId', 'selectedAppId'] as const;
  for (const slice of slices) subscribe(slice, syncHash);
  subscribe('route', syncHash);
  applyFromHash();
}
