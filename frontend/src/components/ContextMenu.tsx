// 右键菜单（18 文档 批 7）。
//
// **为什么需要它。** 应用网格里的一格就是"这一个应用"，而"排除它"这类动作原先只有一条路：
// 到下面的使用明细里找到那一行、点开编辑器。可明细是**按当前周期**统计的，而网格是全量的
// ——周期切到"今天"时，昨天才用过的那个应用在明细里根本没有一行，于是网格上看得见它、却没
// 有任何地方能对它下手。右键是"对着某一个对象的动作"的常规位置，也不占任何版面。
//
// 交互契约与状态点浮层、主题下拉同族（06 文档 §13）：点外面关、Esc 关并把焦点还给触发处、
// 上下键在项之间走。位置跟鼠标（右键菜单的惯例），并**贴边翻转**：靠着视口右/下沿打开时
// 整块翻到另一侧，否则菜单会被裁掉一半。
//
// 挂在 body 上（portal）：网格自己有 `overflow` 与层叠上下文，留在原处会被裁。
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './Icon.tsx';
import type { IconName } from './Icon.tsx';

export interface MenuItem {
  id: string;
  label: string;
  icon?: IconName;
  /** 危险动作：文字换成危险色。当前没有不可撤销的项，留着给以后的"删除数据"。 */
  danger?: boolean;
  onPick: () => void;
}

export interface MenuState {
  /** 鼠标位置（`clientX/clientY`，与 `position: fixed` 同一套坐标）。 */
  x: number;
  y: number;
  /** 菜单顶上那行灰字：说清这些动作作用在谁身上。 */
  title?: string;
  items: readonly MenuItem[];
}

/** 与鼠标的距离：贴着指针会让第一项在打开的瞬间就被 hover 上。 */
const OFFSET = 2;
/** 收边留白。 */
const MARGIN = 8;

export function ContextMenu({ state, onClose }: { state: MenuState; onClose: () => void }) {
  const panel = useRef<HTMLDivElement | null>(null);
  const [placed, setPlaced] = useState({ left: state.x + OFFSET, top: state.y + OFFSET });

  // 量完再定位：菜单宽高取决于最长那一项的文字，事前算不出来。useLayoutEffect 让这次
  // 修正发生在浏览器绘制之前，因此看不到跳动。
  useLayoutEffect(() => {
    const node = panel.current;
    if (!node) return;
    const { width, height } = node.getBoundingClientRect();
    const maxLeft = window.innerWidth - width - MARGIN;
    const maxTop = window.innerHeight - height - MARGIN;
    setPlaced({
      left: Math.max(MARGIN, Math.min(state.x + OFFSET, maxLeft)),
      top: Math.max(MARGIN, Math.min(state.y + OFFSET, maxTop)),
    });
  }, [state.x, state.y, state.items]);

  useEffect(() => {
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
    // pointerdown 而不是 click：按下就关，与主题下拉、应用范围弹层同一套。捕获阶段是为了
    // 抢在别的组件把这次点击吃掉之前。
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && panel.current?.contains(event.target)) return;
      onClose();
    };
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      const items = [...(panel.current?.querySelectorAll<HTMLButtonElement>('button') || [])];
      if (!items.length) return;
      event.preventDefault();
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const step = event.key === 'ArrowDown' ? 1 : -1;
      items[(index + step + items.length) % items.length].focus();
    };
    // 第二次右键：关掉这一个，让调用方开新的那一个（浏览器自己的菜单已被调用方拦掉）。
    document.addEventListener('pointerdown', onPointerDown, true);
    document.addEventListener('keydown', onKeydown, true);
    window.addEventListener('resize', onClose);
    window.addEventListener('scroll', onClose, true);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown, true);
      document.removeEventListener('keydown', onKeydown, true);
      window.removeEventListener('resize', onClose);
      window.removeEventListener('scroll', onClose, true);
    };
  }, [onClose]);

  return createPortal(
    <div
      className="context-menu"
      role="menu"
      aria-label={state.title || '操作'}
      ref={panel}
      style={{ left: `${placed.left}px`, top: `${placed.top}px` }}
    >
      {state.title ? <div className="context-menu__title">{state.title}</div> : null}
      {state.items.map((item) => (
        <button
          className="context-menu__item"
          type="button"
          role="menuitem"
          key={item.id}
          data-danger={item.danger ? 'true' : undefined}
          onClick={() => {
            // 先关再执行：动作里可能弹提示、也可能重取整屏，那时菜单早该不在了。
            onClose();
            item.onPick();
          }}
        >
          {item.icon ? <Icon name={item.icon} /> : null}
          <span className="context-menu__label">{item.label}</span>
        </button>
      ))}
    </div>,
    document.body,
  );
}
