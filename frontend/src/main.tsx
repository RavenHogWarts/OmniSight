// 唯一入口（07 文档 §3）。做五件事，别的都不做：
//   1. 交接令牌、恢复主题、把 React 挂到模板给的几个挂载点上。
//   2. 路由：按 route 动态 import 视图模块，取数、渲染。
//   3. 统一事件委托：模板里的 `data-action` 由这里分发（彻底移除内联 onclick）。
//   4. 键盘快捷键（06 文档 §4.1）。
//   5. SSE 连接与失效重取。
//
// **为什么是多个 React root 而不是一个**：页面外壳（顶栏、标签、周期栏、挂载点）是
// Jinja 模板渲染的，它承担三件 React 给不了的事——`noscript` 提示、CSP 下不必等
// JS 的骨架、以及 `tools/smoke.py` 能在产物上验证挂载点齐全。所以 React 挂进模板
// 给的那几个洞里；跨 root 的状态共享由 core/store.ts 负责（它本来就是外部 store）。
// **样式表也进构建图**（15 文档 §11.4）。Vite 按 `styles/app.css` 里的 @import 顺序把
// 那 30 个文件内联成产物里的一份带哈希的 CSS，模板从清单读它的地址。级联顺序因此仍然
// 只有 app.css 一处真源，而"漏写一条 @import"从「某个组件静默没样式」变成了构建失败。
import '../styles/app.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import type { Root } from 'react-dom/client';
import { Icon } from './components/Icon.tsx';
import { Banners } from './components/degraded.tsx';
import { OverlayHost } from './components/Drawer.tsx';
import { ImportBanner, openImportWizard } from './components/ImportWizard.tsx';
import { maybeShowOnboarding, openAbout } from './components/Onboarding.tsx';
import { PeriodNav, goToday, step as stepPeriod } from './components/PeriodNav.tsx';
import { StatusDot } from './components/StatusDot.tsx';
import { ToastHost, fail } from './components/toast.tsx';
import { TooltipHost, hide as hideTooltip, show as showTooltip } from './components/tooltip.tsx';
import { adoptToken, get as apiGet } from './core/api.ts';
import { on as busOn } from './core/bus.ts';
import { abortPending, fetchInto } from './core/loader.ts';
import { ROUTES, go, start as startRouter } from './core/router.ts';
import { getState, setState, subscribe } from './core/store.ts';
import { connect as connectStream, startPolling } from './core/stream.ts';
import {
  restore as restoreTheme,
  cycle as cycleTheme,
  set as setTheme,
  watchSystem,
} from './core/theme.ts';
import { rangeFromDefaultView } from './domain/metrics.ts';
import { openSettingsDrawer } from './views/settings.tsx';
import type { ViewModule } from './views/types.ts';
import type { SettingField, SettingValue, SettingsResponse, StatusResponse } from './types/api.d.ts';

const VIEW_MODULES: Record<string, () => Promise<ViewModule>> = {
  overview: () => import('./views/overview.tsx'),
  apps: () => import('./views/apps.tsx'),
  keyboard: () => import('./views/keyboard.tsx'),
  insights: () => import('./views/insights.tsx'),
};

/** 模板里的挂载点。少一个就是一块界面消失，所以拿不到时直接抛（core/dom 的老规矩）。 */
function mountPoint(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`挂载点 #${id} 不在模板里`);
  return node;
}

let viewRoot: Root | null = null;
let activeRoute: string | null = null;
let activeModule: ViewModule | null = null;

/** 切换视图。React 负责卸载上一棵树（图表的 ResizeObserver 与总线订阅在 effect 里拆）。 */
async function mountRoute(route: string): Promise<void> {
  if (activeRoute === route) return;
  const load = VIEW_MODULES[route] || VIEW_MODULES.overview;
  let module: ViewModule;
  try {
    module = await load();
  } catch {
    fail('视图加载失败，请刷新页面');
    return;
  }
  activeRoute = route;
  activeModule = module;
  syncTabs(route);
  refresh();
  const { View } = module;
  viewRoot?.render(
    <StrictMode>
      <View />
    </StrictMode>,
  );
  document.title = `${module.title} · OmniSight`;
  // 焦点移到新视图的标题（07 文档 §9）：否则键盘用户切完视图仍停在标签栏上。
  // React 的渲染是同步提交的，但 DOM 要等这一帧——放到微任务之后取。
  window.setTimeout(() => {
    document.querySelector<HTMLElement>('#view-title')?.focus();
  }, 0);
}

function syncTabs(route: string): void {
  for (const id of ROUTES) {
    document.getElementById(`tab-${id}`)?.setAttribute('aria-selected', String(id === route));
  }
  document.getElementById('view-root')?.setAttribute('aria-labelledby', `tab-${route}`);
}

/** 按当前状态重新取数。周期变了要 abort 上一批，否则旧响应会覆盖新数据。 */
function refresh({ abort = true }: { abort?: boolean } = {}): void {
  if (!activeModule) return;
  if (abort) abortPending();
  for (const request of activeModule.needs(getState())) {
    fetchInto(request.key, request.path, request.params || {}, request.options || {});
  }
}

/**
 * data-action 分发表。声明式意图写在模板的标记上，处理集中在这里（07 文档 §7）。
 *
 * React 化之后它只服务**模板里那些标记**（顶栏标签、设置页里的两个按钮）——React
 * 组件里的按钮直接写 onClick，不必绕这一圈。
 */
const ACTIONS: Record<string, (dataset: DOMStringMap) => void> = {
  'route:go': (dataset) => go(dataset.route || 'overview'),
  'theme:cycle': () => cycleTheme(),
  'settings:open': () => {
    void openSettingsDrawer(() => {
      void loadStatus();
      refresh({ abort: false });
    });
  },
  'import:open': () => openImportWizard(),
  'about:open': () => {
    void openAbout();
  },
  'period:prev': () => stepPeriod(-1),
  'period:next': () => stepPeriod(1),
  'period:today': () => goToday(),
};

function installDelegation(): void {
  document.addEventListener('click', (event) => {
    const target = (event.target as Element | null)?.closest<HTMLElement>('[data-action]');
    if (!target) return;
    const handler = ACTIONS[target.dataset.action || ''];
    if (handler) handler(target.dataset);
  });
}

/** 快捷键（06 文档 §4.1）。输入框里一律不拦截，否则用户没法在搜索框里打 4。 */
function installShortcuts(): void {
  document.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const tag = ((event.target as Element | null)?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return;
    const index = ['1', '2', '3', '4'].indexOf(event.key);
    if (index >= 0) {
      go(ROUTES[index]);
      return;
    }
    if (event.key === 'ArrowLeft') stepPeriod(-1);
    else if (event.key === 'ArrowRight') stepPeriod(1);
    else if (event.key === 't' || event.key === 'T') goToday();
    else if (event.key === '/') {
      const search = document.querySelector<HTMLElement>('.search input');
      if (search) {
        event.preventDefault();
        search.focus();
      }
    } else if (event.key === '?') showShortcutHelp();
  });
}

function showShortcutHelp(): void {
  showTooltip({
    title: '键盘快捷键',
    rows: [
      ['1 - 4', '切换视图'],
      ['左 / 右', '上一个 / 下一个周期'],
      ['T', '回到今天'],
      ['/', '聚焦搜索'],
      ['方向键', '在键盘热力图上移动'],
    ],
    x: window.innerWidth / 2 - 120,
    y: window.innerHeight / 2 - 80,
  });
  window.setTimeout(hideTooltip, 4000);
}

async function loadStatus(): Promise<StatusResponse | null> {
  try {
    const status = (await apiGet('/status')) as StatusResponse;
    setState('status', status);
    setState('capabilities', status.capabilities || null);
    setState('degraded', status.degraded || []);
    return status;
  } catch {
    // 状态取不到时不要把整页变成错误：各面板自己的错误态更有用。
    setState('degraded', [
      {
        code: 'status_unreachable',
        severity: 'error',
        title: '无法读取运行状态',
        detail: '采集进程可能已退出，或访问令牌已失效。图表显示的可能是缓存数据。',
        hint: '从托盘菜单重新打开仪表盘',
        // 后端的 DegradedNotice 一定带 docs（可为 null）。这条是前端造的，也得对齐。
        docs: null,
      },
    ]);
    return null;
  }
}

/** 读一条设置的当前值。 */
function valueOf(
  settings: Record<string, SettingField>,
  key: string,
  fallback: SettingValue,
): SettingValue {
  const spec = settings[key];
  return spec && spec.value !== null && spec.value !== undefined ? spec.value : fallback;
}

/** 首屏读一次设置：周起始日、默认周期、键盘布局都是**后端配置**，前端不猜。 */
async function loadPrefs(): Promise<void> {
  try {
    const payload = (await apiGet('/settings')) as SettingsResponse;
    setState('settings', payload);
    const settings = payload.settings || {};
    setState('prefs', {
      weekStartsOn: Number(valueOf(settings, 'ui.week_starts_on', 0)),
      defaultRange: rangeFromDefaultView(String(valueOf(settings, 'ui.default_view', 'daily'))),
      keyboardLayout: String(valueOf(settings, 'ui.keyboard_layout', 'auto')),
      titlesRecorded: Boolean(valueOf(settings, 'privacy.record_window_titles', false)),
    });
    const theme = String(valueOf(settings, 'ui.theme', 'system'));
    // 静态导入。原先这里 `await import('./core/theme.ts')`，而同一个模块在文件顶部
    // 已经静态导入过——Rollup 会为此报 INEFFECTIVE_DYNAMIC_IMPORT：模块本来就在入口
    // 分包里，动态导入省不下任何字节，只是让这一行多等一个微任务。
    if (theme !== getState().theme) setTheme(theme);
  } catch {
    // 设置读不到就用默认值，界面照常可用。
  }
}

/**
 * 取数订阅。**渲染不在这里**：React 组件各自订阅自己关心的切片（core/useStore.ts），
 * 数据到位就自己重画。这里只管"什么变化要重新发请求"。
 *
 * 这是 React 化省掉的一整块：原先有八个切片订阅同一个 `rerender()`，因为渲染是
 * 手写的、必须有人来喊一声。
 */
function installSubscriptions(): void {
  subscribe('period', () => refresh());
  subscribe('metric', () => refresh());
  subscribe('scopeAppId', () => refresh());
  subscribe('selectedKeyId', () => refresh());

  // SSE 说"有新数据了"。它不知道前端在看哪个周期，所以由前端决定要不要重取
  // （07 文档 §5.3）。看历史周期时不重取：那些数据不会再变。
  busOn('data:invalidated', () => {
    const meta = getState().periodMeta;
    if (!meta || meta.is_current) refresh({ abort: false });
  });
}

/** 挂进模板给的那几个洞。它们互不嵌套，状态经 core/store.ts 共享。 */
function mountShell(): void {
  createRoot(mountPoint('banners')).render(
    <StrictMode>
      <Banners />
      <ImportBanner />
    </StrictMode>,
  );
  createRoot(mountPoint('status-host')).render(
    <StrictMode>
      <StatusDot />
      <ThemeButton />
      <SettingsButton />
    </StrictMode>,
  );
  createRoot(mountPoint('periodbar')).render(
    <StrictMode>
      <PeriodNav />
    </StrictMode>,
  );
  createRoot(mountPoint('toasts')).render(
    <StrictMode>
      <ToastHost />
    </StrictMode>,
  );
  createRoot(mountPoint('overlays')).render(
    <StrictMode>
      <OverlayHost />
      <TooltipHost />
    </StrictMode>,
  );
  viewRoot = createRoot(mountPoint('view-root'));
}


/** 主题三态循环（跟随系统 / 浅 / 深）。图标是 contrast，不是日月——见 Icon.tsx 的理由。 */
function ThemeButton() {
  return (
    <button
      className="icon-button"
      type="button"
      id="theme-toggle"
      title="切换主题"
      aria-label="切换主题"
      onClick={() => cycleTheme()}
    >
      <Icon name="theme" />
    </button>
  );
}

function SettingsButton() {
  return (
    <button
      className="icon-button"
      type="button"
      title="设置"
      aria-label="打开设置"
      onClick={() => ACTIONS['settings:open']({} as DOMStringMap)}
    >
      <Icon name="gear" />
    </button>
  );
}
async function main(): Promise<void> {
  const script = document.querySelector<HTMLScriptElement>('script[data-token]');
  const token = adoptToken(script ? script.dataset.token : '');
  restoreTheme();
  watchSystem();

  mountShell();
  installDelegation();
  installShortcuts();
  installSubscriptions();

  if (!token) {
    viewRoot?.render(
      <div className="card">
        <h2>缺少访问令牌</h2>
        <p className="muted">
          请从托盘菜单重新打开仪表盘。令牌只在打开时经 URL 交接一次，刷新后仍然有效。
        </p>
      </div>,
    );
    return;
  }

  // 顺序是刻意的：先读状态与配置，再让路由填 store，最后才装 route 订阅并挂载视图。
  // 这时 activeModule 还是 null，所以中间几次 setState 触发的 refresh() 都是空转。
  //
  // `#about` 必须在 startRouter() 之前读走：路由不认识它，会把 hash 改写成
  // `#/overview?range=day`，之后就再也看不出用户是从托盘的「关于与隐私说明」进来的。
  const wantsAbout = window.location.hash.replace(/^#\/?/, '') === 'about';
  await Promise.all([loadStatus(), loadPrefs()]);
  startRouter();
  // 首次进入且 URL 没带 range 时，用配置里的默认周期（ui.default_view）。
  if (!window.location.hash.includes('range=')) {
    setState('period', { ...getState().period, range: getState().prefs.defaultRange });
  }
  subscribe('route', (route) => {
    void mountRoute(route);
  });
  await mountRoute(getState().route);

  const settings = getState().settings;
  if (settings && !valueOf(settings.settings || {}, 'privacy.realtime_stream', true)) {
    // 用户关掉了实时流：直接进轮询，不去敲一个必然 404 的端点。
    startPolling();
  } else {
    connectStream();
  }

  // 首启说明放在最后：仪表盘已经画完，说明浮在它上面。它自己判断要不要出现
  // （后端的 `required`），不在这里猜（08 文档 §6.1）。
  if (wantsAbout) void openAbout();
  else void maybeShowOnboarding();
}

void main();
