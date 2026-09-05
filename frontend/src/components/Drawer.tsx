// 抽屉：焦点陷阱 + Esc 关闭 + 归还焦点（06 文档 §13）。
//
// 焦点陷阱不是装饰：抽屉打开后 Tab 键若能走到底下的页面，键盘用户会"掉出"抽屉且
// 看不到自己在哪。归还焦点同理——关掉抽屉后焦点必须回到打开它的那个按钮。
//
// **打开方式仍然是命令式的**（`openOverlay(<SettingsDrawer/>)`）：设置、导入向导、
// 首启说明分别由工具条、横幅按钮、后端的 `required` 触发，它们不在同一棵子树里，
// 让每一处都往上抬一个 `open` 状态只会把这三件事的开关散到三个地方。
//
// 设置抽屉是**两种落脚处之一**（`ui.settings_surface`，18 文档 §2.1）：另一种是 `/settings`
// 那一页。正文是同一个组件（pages/SettingsPage.tsx），因此没有"抽屉版设置"这种东西。
import { useEffect, useRef, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { Icon } from './Icon.tsx';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])';

// ── 覆盖层的外部 store ────────────────────────────────────────────────
let overlay: ReactNode = null;
const listeners = new Set<() => void>();

function publish(next: ReactNode): void {
  overlay = next;
  for (const listener of [...listeners]) listener();
}

/** 打开一个覆盖层。同一时刻只有一个——第二次调用替换掉前一个。 */
export function openOverlay(node: ReactNode): void {
  publish(node);
}

export function closeOverlay(): void {
  if (overlay !== null) publish(null);
}

/** 挂在模板的 `#overlays` 里。 */
export function OverlayHost() {
  const current = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => overlay,
  );
  return <>{current}</>;
}

// ── 抽屉本体 ──────────────────────────────────────────────────────────
export interface DrawerProps {
  title: string;
  children?: ReactNode;
  footer?: ReactNode;
  onClose?: (() => void) | null;
  /** 宽一档（560px）。设置抽屉要它：一行设置是"标签 + 控件"两栏，420px 里两栏会挤成一栏。 */
  wide?: boolean;
}

export function Drawer({ title, children, footer, onClose = null, wide = false }: DrawerProps) {
  const panel = useRef<HTMLElement | null>(null);
  const closeButton = useRef<HTMLButtonElement | null>(null);
  // 打开它的那个元素。**在挂载前读**：挂载后 activeElement 已经变了。
  const opener = useRef<HTMLElement | null>(
    typeof document === 'undefined' ? null : (document.activeElement as HTMLElement | null),
  );

  const close = () => {
    closeOverlay();
    onClose?.();
    const previous = opener.current;
    if (previous && typeof previous.focus === 'function') previous.focus();
  };
  // close 会被 effect 里的键盘处理器引用，而那个 effect 只装一次。
  const closeRef = useRef(close);
  closeRef.current = close;

  useEffect(() => {
    closeButton.current?.focus();
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const root = panel.current;
      if (!root) return;
      const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
        (node) => node.offsetParent !== null,
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!root.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
    };
    // 捕获阶段：抽屉里的输入框也可能监听 Escape，先到先得。
    document.addEventListener('keydown', onKeydown, true);
    return () => document.removeEventListener('keydown', onKeydown, true);
  }, []);

  return (
    <>
      <div className="scrim" onClick={close} />
      <aside
        className={wide ? 'drawer drawer--wide' : 'drawer'}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={panel}
      >
        <div className="drawer__head">
          <h2>{title}</h2>
          <span className="spacer" />
          <button
            className="icon-button"
            type="button"
            aria-label="关闭"
            onClick={close}
            ref={closeButton}
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="drawer__body">{children}</div>
        {footer ? <div className="drawer__foot">{footer}</div> : null}
      </aside>
    </>
  );
}
