// 仪表盘的入口（07 文档 §3）。做五件事，别的都不做：
//   1. 路由：按 route 动态 import 视图模块，取数、渲染。
//   2. 统一事件委托：模板里的 `data-action` 由这里分发（彻底移除内联 onclick）。
//   3. 键盘快捷键（06 文档 §4.1）。
//   4. SSE 连接与失效重取。
//   5. 首启说明（08 文档 §6.1 要求的那一次模态确认）。
//
// **它不再是唯一入口**（18 文档 批 1）：设置与关于各自是一张独立页面，各有一个入口
// （`settings.tsx` / `about.tsx`）。三者共用的开场——接令牌、恢复主题、工具条与三个浮层
// ——收在 pages/shell.tsx，因此这个文件里只剩仪表盘独有的东西。设置另有一档是**就地开在
// 抽屉里**（`ui.settings_surface`，18 文档 §2.1）：那一份按需 `import()`，见 SettingsEntry。
//
// **为什么是多个 React root 而不是一个**：页面外壳（工具条、标签、周期栏、挂载点）是
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
import { ImportBanner, openImportWizard } from './components/ImportWizard.tsx';
import { maybeShowOnboarding } from './components/Onboarding.tsx';
import { DateBar, RangeBar, goToday, step as stepPeriod } from './components/PeriodNav.tsx';
import { fail } from './components/toast.tsx';
import { hide as hideTooltip, show as showTooltip } from './components/tooltip.tsx';
import { get as apiGet } from './core/api.ts';
import { on as busOn } from './core/bus.ts';
import { abortPending, fetchInto } from './core/loader.ts';
import { ROUTES, go, start as startRouter } from './core/router.ts';
import { getState, setState, subscribe } from './core/store.ts';
import { connect as connectStream, startPolling } from './core/stream.ts';
import { set as setTheme, setHeat } from './core/theme.ts';
import { useSlice } from './core/useStore.ts';
import { rangeFromDefaultView } from './domain/metrics.ts';
import {
  MissingToken,
  PageLink,
  adopt,
  loadStatus,
  mountChrome,
  mountPoint,
} from './pages/shell.tsx';
import type { ViewModule } from './views/types.ts';
import type { SettingField, SettingValue, SettingsResponse } from './types/api.d.ts';

const VIEW_MODULES: Record<string, () => Promise<ViewModule>> = {
  overview: () => import('./views/overview.tsx'),
  apps: () => import('./views/apps.tsx'),
  keyboard: () => import('./views/keyboard.tsx'),
  insights: () => import('./views/insights.tsx'),
};

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
  // 外壳宽度按路由取值（17 文档 §4.1）：总览/洞察 1080px（TimeLens），键盘/应用
  // 1280px（KeyTrace 的机身 min-width 加 padding 正好落在 1280 内）。切换点是这一个
  // 属性，layout.css 里 `body[data-route]` 各自覆盖 --shell-max 与 --layout-gutter。
  document.body.dataset.route = route;
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
 * React 化之后它只服务**模板里那些标记**（视图标签栏）——React 组件里的按钮直接写
 * onClick，不必绕这一圈。设置与关于原先也在这张表里（`settings:open` / `about:open`），
 * 18 文档 批 1 之后它们各有一个地址，由工具条右段那个槽负责（PageLink / SettingsEntry）。
 */
const ACTIONS: Record<string, (dataset: DOMStringMap) => void> = {
  'route:go': (dataset) => go(dataset.route || 'overview'),
  'import:open': () => openImportWizard(),
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

/** 读一条设置的当前值。 */
function valueOf(
  settings: Record<string, SettingField>,
  key: string,
  fallback: SettingValue,
): SettingValue {
  const spec = settings[key];
  return spec && spec.value !== null && spec.value !== undefined ? spec.value : fallback;
}

/**
 * 最近一次读到的设置全文。**判据是"这一份与上一份一样吗"，不是"有人喊了一声"**：轮询
 * 那一路每 30 秒都会喊一次（它分不清变没变，见 core/stream.ts 的说明），而每喊一次就要
 * 重取当前视图那四五个请求，只为了发现什么都没改。
 */
let settingsFingerprint = '';

/**
 * 读一次设置：周起始日、默认周期、键盘布局、设置的打开方式都是**后端配置**，前端不猜。
 *
 * @returns 与上一次读到的相比变了吗（第一次总是变）
 */
async function loadPrefs(): Promise<boolean> {
  try {
    const payload = (await apiGet('/settings')) as SettingsResponse;
    const settings = payload.settings || {};
    // 键序由后端的 SPECS 决定，因此同一份配置的字符串是稳定的。
    const fingerprint = JSON.stringify(settings);
    const changed = fingerprint !== settingsFingerprint;
    settingsFingerprint = fingerprint;
    setState('settings', payload);
    setState('prefs', {
      weekStartsOn: Number(valueOf(settings, 'ui.week_starts_on', 0)),
      defaultRange: rangeFromDefaultView(String(valueOf(settings, 'ui.default_view', 'daily'))),
      keyboardLayout: String(valueOf(settings, 'ui.keyboard_layout', 'auto')),
      titlesRecorded: Boolean(valueOf(settings, 'privacy.record_window_titles', false)),
      settingsSurface: String(valueOf(settings, 'ui.settings_surface', 'drawer')),
    });
    const theme = String(valueOf(settings, 'ui.theme', 'system'));
    // 静态导入。原先这里 `await import('./core/theme.ts')`，而同一个模块在文件顶部
    // 已经静态导入过——Rollup 会为此报 INEFFECTIVE_DYNAMIC_IMPORT：模块本来就在入口
    // 分包里，动态导入省不下任何字节，只是让这一行多等一个微任务。
    if (theme !== getState().theme) setTheme(theme);
    // 热力色同理（18 文档 批 3 起它是 `ui.heat`）。在另一个标签页里改了色阶，这一页
    // 经 `settings:changed` 走到这里就跟着换。
    const heat = String(valueOf(settings, 'ui.heat', 'blue'));
    if (heat !== getState().heat) setHeat(heat);
    return changed;
  } catch {
    // 设置读不到就用默认值，界面照常可用。
    return false;
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

  // 设置被改了（18 文档 §2.1）。三个来源同一条总线：**这一页的设置抽屉**（改完就在
  // 旁边，"周起始日改了而图表还按旧的切周"会当场被看见）、**另一个标签页**（服务端在
  // 配置落盘后广播 `settings` 帧，presentation/stream.py）、以及轮询那一路的兜底。
  //
  // 重取按"真的变了"来（loadPrefs 的返回值）：轮询每 30 秒喊一次，而无条件重取意味着
  // 一个空闲的仪表盘每半分钟把整屏数据重来一遍。
  busOn('settings:changed', () => {
    void loadPrefs().then((changed) => {
      if (changed) refresh({ abort: false });
    });
  });
}

/**
 * 挂进模板给的那几个洞。它们互不嵌套，状态经 core/store.ts 共享。
 *
 * 工具条与三个浮层由 pages/shell.tsx 统一挂（三页共用）；这里只剩仪表盘独有的两条控件带
 * 与视图根。工具条右段那个槽在这一页是 ⚙，它去哪儿由配置决定（见 SettingsEntry）。
 */
function mountShell(): void {
  mountChrome({
    nav: (
      <>
        <ImportButton />
        <SettingsEntry />
      </>
    ),
    banners: <ImportBanner />,
  });
  // 两条居中控件带（17 文档 §4.1）。`#periodbar` 的 id 沿用，类名换成 `.datebar`
  // ——smoke 与契约测试验的是 id。
  createRoot(mountPoint('periodbar')).render(
    <StrictMode>
      <DateBar />
    </StrictMode>,
  );
  createRoot(mountPoint('rangebar')).render(
    <StrictMode>
      <RangeBar />
    </StrictMode>,
  );
  viewRoot = createRoot(mountPoint('view-root'));
}

/**
 * 导入向导的入口（17 文档 §4.1 的第四个功能钮）。
 *
 * 它有三个入口，各自的场合不同：这个钮（随时想导入）、`ImportBanner`（首次发现旧数据时
 * 主动提示一次）、以及设置页「数据」段里那个按钮（在"数据"这件事的语境里）。三者调的是
 * 同一个 `openImportWizard()`。
 */
function ImportButton() {
  return (
    <button
      className="icon-button"
      type="button"
      title="从旧版导入"
      aria-label="从旧版导入数据"
      onClick={() => openImportWizard()}
    >
      <Icon name="download" />
    </button>
  );
}

/**
 * ⚙。**它去哪儿由配置决定**（`ui.settings_surface`，18 文档 §2.1）：抽屉开在仪表盘右侧，
 * 或者跳到 `/settings` 那一页。原先它一律 `target="_blank"`，而"每点一次设置就多攒一个
 * 标签页"没有任何设置关得掉——这是这次改动的起点。
 *
 * 两档下它都是**一个真链接**（`href` 始终指向 `/settings`），抽屉只接管不带修饰键的左键
 * 点击，因此 Ctrl+点击、中键、右键「在新标签页打开」仍然有效（pages/shell.tsx:PageLink）。
 *
 * 读 store 里的 prefs 而不是渲染时算好的常量：这一项在抽屉里就能改，改完**下一次点击**
 * 必须已经按新的走（`settings:changed` -> loadPrefs -> 这里重渲染）。
 */
function SettingsEntry() {
  const prefs = useSlice('prefs');
  const drawer = prefs.settingsSurface === 'drawer';
  return (
    <PageLink href="/settings" icon="gear" label="设置" onActivate={drawer ? openSettings : null} />
  );
}

/** 抽屉那一份按需加载：首屏不为一个可能不点的面板付表单代码的钱（与四个视图同一个手法）。 */
function openSettings(): void {
  void import('./pages/SettingsDrawer.tsx')
    .then((module) => module.openSettingsDrawer())
    .catch(() => fail('设置面板加载失败，请刷新页面'));
}

async function main(): Promise<void> {
  // 接令牌、恢复主题、看系统深浅——三页共用的开场（pages/shell.tsx）。
  const token = adopt();

  mountShell();
  installDelegation();
  installShortcuts();
  installSubscriptions();

  if (!token) {
    viewRoot?.render(<MissingToken />);
    return;
  }

  // 顺序是刻意的：先读状态与配置，再让路由填 store，最后才装 route 订阅并挂载视图。
  // 这时 activeModule 还是 null，所以中间几次 setState 触发的 refresh() 都是空转。
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
  // （后端的 `required`），不在这里猜（08 文档 §6.1）。**只有首启那一次是模态**——
  // 随时查看的那一份是 `/about` 那一页（18 文档 批 4），托盘与设置页都指向它。
  void maybeShowOnboarding();
}

void main();
