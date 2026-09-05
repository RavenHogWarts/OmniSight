// 三个页面共用的外壳装配（18 文档 批 1）。
//
// 仪表盘、设置页、关于页各有一个入口（`main.tsx` / `settings.tsx` / `about.tsx`），而它们
// 开头三件事完全一样：接令牌、恢复主题、把工具条与三个浮层挂到模板给的洞里。抽在这里，
// 于是"每个页面都要做的事"只有一处真源；各入口里剩下的就是那一页独有的东西（仪表盘的
// 路由/周期/SSE、设置页的表单、关于页的说明）。
//
// **为什么设置与关于是独立页面而不是抽屉与模态**：四条居中控件带（日期/范围/视图/指标）
// 长在 Jinja 模板里，一个 hash 路由的设置页顶上会挂着一个日期导航；靠 CSS 藏掉它们，
// 那些按钮仍然在 Tab 序列上，而视图切换器会进入"四个标签全未选中"的状态。
import { StrictMode } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { OverlayHost } from '../components/Drawer.tsx';
import { Icon } from '../components/Icon.tsx';
import type { IconName } from '../components/Icon.tsx';
import { StatusDot } from '../components/StatusDot.tsx';
import { ThemeMenu } from '../components/ThemeMenu.tsx';
import { Veil } from '../components/Veil.tsx';
import { Banners } from '../components/degraded.tsx';
import { ToastHost } from '../components/toast.tsx';
import { TooltipHost } from '../components/tooltip.tsx';
import { adoptToken, get as apiGet, tokenParam } from '../core/api.ts';
import { setState } from '../core/store.ts';
import { restore as restoreTheme, watchSystem } from '../core/theme.ts';
import type { StatusResponse } from '../types/api.d.ts';

/** 模板里的挂载点。少一个就是一块界面消失，所以拿不到时直接抛（core/dom 的老规矩）。 */
export function mountPoint(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error(`挂载点 #${id} 不在模板里`);
  return node;
}

/**
 * 接令牌 + 恢复主题。**每个入口的第一句**。
 *
 * @returns 拿到的令牌；空串表示这一页没有令牌（页面自己决定怎么说明）。
 */
export function adopt(): string {
  const script = document.querySelector<HTMLScriptElement>('script[data-token]');
  const token = adoptToken(script ? script.dataset.token : '');
  restoreTheme();
  watchSystem();
  return token;
}

/**
 * 跨页地址。**一律带令牌。**
 *
 * 令牌存在 sessionStorage 里（`core/api.ts:adoptToken`），而 sessionStorage **不跨标签页
 * 可靠共享**：Ctrl+点击、右键"在新标签页打开"、以及托盘拉起的新窗口都拿不到副本。同一
 * 标签页内导航其实不需要带，但两种情形在同一个 href 上分不开，而多一个查询参数没有代价
 * ——`adoptToken` 收下它之后会立刻从地址栏抹掉。
 */
export function pageUrl(path: string): string {
  return `${path}?token=${encodeURIComponent(tokenParam())}`;
}

/**
 * 工具条右段那个随页而变的槽：⚙ 去设置、⌂ 回仪表盘。**一律同一标签页**（18 文档 §2.1）
 * ——原先 ⚙ 是 `target="_blank"`，而"每次点设置都多一个标签"没有任何设置能关掉它。
 *
 * `onActivate` 让调用方接管**不带修饰键的左键点击**（仪表盘用它开设置抽屉）。给了它之后
 * 这仍然是一个真链接：Ctrl/Shift/中键点击、右键"在新标签页打开"、以及把它拖到书签栏，
 * 走的都还是 `href`。判断在这里做一次，而不是让每个调用方各写一遍那五个条件。
 */
export function PageLink({
  href,
  icon,
  label,
  onActivate = null,
}: {
  href: string;
  icon: IconName;
  label: string;
  onActivate?: (() => void) | null;
}) {
  return (
    <a
      className="icon-button"
      href={pageUrl(href)}
      title={label}
      aria-label={label}
      onClick={
        onActivate
          ? (event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
              if (event.button !== 0) return;
              event.preventDefault();
              onActivate();
            }
          : undefined
      }
    >
      <Icon name={icon} />
    </a>
  );
}

/**
 * 工具条右段 + 三个浮层宿主。三页共用。
 *
 * @param nav 页面切换槽（`<PageLink>`）
 * @param banners 追加的横幅（仪表盘的导入提示、设置页的"待重启"提示）
 */
export function mountChrome({ nav, banners }: { nav?: ReactNode; banners?: ReactNode } = {}): void {
  createRoot(mountPoint('banners')).render(
    <StrictMode>
      <Banners />
      {banners}
    </StrictMode>,
  );
  // 状态点在三页都在：它回答的"采集还在跑吗"与用户此刻看哪一页无关。
  createRoot(mountPoint('status-host')).render(
    <StrictMode>
      <StatusDot />
      {nav}
      <ThemeMenu />
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
      <Veil />
    </StrictMode>,
  );
}

/**
 * 读运行状态。状态点、能力清单与"采集异常"横幅都读它，因此三页都要取一次。
 *
 * 取不到时不把整页变成错误：各面板自己的错误态更有用。
 */
export async function loadStatus(): Promise<StatusResponse | null> {
  try {
    const status = (await apiGet('/status')) as StatusResponse;
    setState('status', status);
    setState('capabilities', status.capabilities || null);
    setState('degraded', status.degraded || []);
    return status;
  } catch {
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

/** 缺令牌时三页共用的说明卡。令牌只在打开时经 URL 交接一次（08 文档 §3.2b）。 */
export function MissingToken() {
  return (
    <div className="card">
      <h2>缺少访问令牌</h2>
      <p className="muted">
        请从托盘菜单重新打开仪表盘。令牌只在打开时经 URL 交接一次，同一标签页内刷新仍然有效。
      </p>
    </div>
  );
}
