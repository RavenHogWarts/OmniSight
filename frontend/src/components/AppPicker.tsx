// 应用范围选择器（06 文档 §7 改进 3、14 文档 §2.19 P3-4、§4.6 第 3 项）。
//
// "全部应用 / 某个应用"是同一张热力图的两种范围，不是两个功能。原 KeyTrace 把它放在
// 页面最下方一个独立面板里，还需要另外连上 TimeLens——合并后它只是键盘卡头上的一个按钮。
//
// **网格本身在 AppGrid.tsx**（17 文档 §4.4）：同一份实现在应用视图里是一整块常驻面板
// （KeyTrace 的那一屏），在这里收进弹层。这个文件只剩下"触发器 + 弹层 + 焦点陷阱"。
import { useEffect, useRef, useState } from 'react';
import { getState, setState } from '../core/store.ts';
import { useSlice } from '../core/useStore.ts';
import { AppGrid, Mark } from './AppGrid.tsx';
import type { PickerApp } from './AppGrid.tsx';
import { Icon } from './Icon.tsx';

const FOCUSABLE = 'button:not([disabled]), input:not([disabled])';

export type { PickerApp };

export interface AppPickerProps {
  apps: readonly PickerApp[] | undefined;
  /** `/apps/running` 里**已记录**应用的 id 集合。 */
  runningIds?: Iterable<number>;
  onChange?: ((appId: number | null) => void) | null;
}

export function AppPicker({ apps, runningIds = [], onChange = null }: AppPickerProps) {
  const scopeAppId = useSlice('scopeAppId');
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  const list = apps || [];

  // 选中的应用在新周期里不存在了：如实回落到全部，而不是显示一个空的过滤。
  useEffect(() => {
    const current = getState().scopeAppId;
    if (current && list.length && !list.some((app) => app.app_id === current)) {
      setState('scopeAppId', null);
    }
  }, [list]);

  // Esc 关闭、Tab 在弹层内循环——与抽屉同一套约定（06 文档 §13）。
  useEffect(() => {
    if (!open) return;
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
        return;
      }
      if (event.key !== 'Tab') return;
      const host = panel.current;
      if (!host) return;
      const items = [...host.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
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
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('keydown', onKeydown, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => {
      document.removeEventListener('keydown', onKeydown, true);
      document.removeEventListener('pointerdown', onPointerDown, true);
    };
  }, [open]);

  const pick = (appId: number | null) => {
    setState('scopeAppId', appId);
    setOpen(false);
    trigger.current?.focus();
    onChange?.(appId);
  };

  const current = list.find((app) => app.app_id === scopeAppId) || null;

  return (
    <div className="app-picker" ref={root}>
      <span className="muted text-sm">范围</span>
      <button
        className="button app-picker__trigger"
        type="button"
        ref={trigger}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="app-picker__mark">{current ? <Mark app={current} /> : null}</span>
        <span className="app-picker__name">
          {current ? current.user_alias || current.display_name : '全部应用'}
        </span>
        <Icon name="down" size={14} />
      </button>
      <div
        className="app-picker__panel"
        ref={panel}
        hidden={!open}
        role="dialog"
        aria-label="选择应用范围"
      >
        <AppGrid
          apps={list}
          runningIds={runningIds}
          selectedId={scopeAppId}
          onPick={pick}
          searchKey={open ? 'open' : 'closed'}
        />
      </div>
    </div>
  );
}
