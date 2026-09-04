// 单例浮动提示（06 文档 §10）。canvas 没有 DOM 节点，命中检测在图表里做，
// 这里只负责定位与内容——现状柱状图完全没有 tooltip，只能看轮廓。
//
// 与 toast 同一个形状（外部 store + React 宿主）：`show()` 的调用者是 Chart 的
// pointermove 回调，每次移动都会调，走 React 的 state 会让整棵子树在指针移动时
// 重渲染。这里只让宿主一个组件重渲染。
import { useLayoutEffect, useRef, useSyncExternalStore } from 'react';

export type TooltipRow = readonly [string, string | number];

export interface TooltipState {
  open: boolean;
  title?: string;
  rows: readonly TooltipRow[];
  /** "该日无应用归因"这类说明（06 文档 §4.2 第三级）。 */
  note?: string;
  x: number;
  y: number;
}

const CLOSED: TooltipState = { open: false, rows: [], x: 0, y: 0 };

let state: TooltipState = CLOSED;
const listeners = new Set<() => void>();

function publish(next: TooltipState): void {
  state = next;
  for (const listener of [...listeners]) listener();
}

export function show(options: Omit<TooltipState, 'open'> & { open?: boolean }): void {
  publish({ ...options, rows: options.rows || [], open: true });
}

export function hide(): void {
  if (state.open) publish(CLOSED);
}

export function TooltipHost() {
  const current = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => state,
  );
  const node = useRef<HTMLDivElement | null>(null);

  // 靠近视口边界时翻转，而不是被裁掉。**必须在布局阶段量**：要先知道自己多大。
  useLayoutEffect(() => {
    const tip = node.current;
    if (!tip || !current.open) return;
    const rect = tip.getBoundingClientRect();
    const margin = 12;
    let left = current.x + margin;
    let top = current.y + margin;
    if (left + rect.width > window.innerWidth - margin) left = current.x - rect.width - margin;
    if (top + rect.height > window.innerHeight - margin) top = current.y - rect.height - margin;
    tip.style.left = `${Math.max(margin, left)}px`;
    tip.style.top = `${Math.max(margin, top)}px`;
  }, [current]);

  return (
    <div
      ref={node}
      className="tooltip"
      role="tooltip"
      aria-hidden={current.open ? undefined : 'true'}
      data-open={current.open ? 'true' : 'false'}
    >
      {current.title ? <div className="tooltip__title">{current.title}</div> : null}
      {current.rows.map(([label, value]) => (
        <div className="tooltip__row" key={label}>
          <span>{label}</span>
          <span>{String(value)}</span>
        </div>
      ))}
      {current.note ? <div className="tooltip__note">{current.note}</div> : null}
    </div>
  );
}
