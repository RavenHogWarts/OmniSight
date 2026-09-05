// 主题下拉（06 文档 §3.1、17 文档 §4.1 的第二个功能钮）。
//
// **为什么不再是那个循环钮**：原先点一下换一档（跟随系统 → 浅色 → 深色 → …）。三态循环钮
// 的代价都落在同一处——一个图标位既说不出"现在是哪一档"，也说不出"还剩哪几档"，所以那时
// 图标刻意用 Contrast 而不是日月（日月会暗示只有两态，见 Icon.tsx 那张映射表）。列表把三档
// 同时摊开之后这两条都不成立了：当前值有勾、另外两档有名字，触发钮因此可以改回**当前那一档
// 本身的图标**——显示器 / 太阳 / 月亮。
//
// 交互契约与状态点浮层、应用范围弹层同族（06 文档 §13）：点外面关、Esc 关并把焦点还给触发
// 钮。**但选项之间走方向键而不是 Tab**：这是 ARIA 的 menu 模式（触发钮 aria-haspopup="menu"、
// 每行 menuitemradio），Tab 在菜单里的语义是"离开菜单"，不是"下一个选项"。
import { useEffect, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { THEMES, isTheme, set as setTheme } from '../core/theme.ts';
import type { Theme } from '../core/theme.ts';
import { useSlice } from '../core/useStore.ts';
import { Icon } from './Icon.tsx';
import type { IconName } from './Icon.tsx';

/**
 * 三档的文案与图标。**写成 Record<Theme, …> 而不是数组**：core/theme.ts 的 THEMES 里多一档
 * 而这里忘了配，编译期就红——"菜单静默少一行"属于只有用户会发现的那类缺陷。顺序也不在这里
 * 定，跟着 THEMES 走（跟随系统在最前，它是默认值）。
 */
const OPTIONS: Record<Theme, { label: string; icon: IconName }> = {
  system: { label: '跟随系统', icon: 'theme-system' },
  light: { label: '浅色', icon: 'theme-light' },
  dark: { label: '深色', icon: 'theme-dark' },
};

/** 面板里的三行。DOM 查询而不是三个 ref：行是 map 出来的，ref 数组还得自己对齐下标。 */
function itemsOf(panel: HTMLElement | null): HTMLButtonElement[] {
  return panel ? [...panel.querySelectorAll<HTMLButtonElement>('button')] : [];
}

export function ThemeMenu() {
  // store 里的 theme 是 string（它还要承接服务端 `ui.theme` 的值），所以这里过一次门。
  const stored = useSlice('theme');
  const theme: Theme = isTheme(stored) ? stored : 'system';
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  // 点外面关掉。用 pointerdown 而不是 click：按下就关，不必等松手；捕获阶段是为了
  // 抢在别的组件把这次点击吃掉之前（与 AppPicker 同一套）。
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target)) return;
      setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown, true);
    return () => document.removeEventListener('pointerdown', onPointerDown, true);
  }, [open]);

  // 打开时焦点落在当前那一档：菜单模式下焦点必须先进菜单，否则方向键无处可去。
  useEffect(() => {
    if (!open) return;
    const items = itemsOf(panel.current);
    items[Math.max(0, THEMES.indexOf(theme))]?.focus();
  }, [open, theme]);

  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };

  const pick = (value: Theme) => {
    setTheme(value);
    close();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === 'Tab') {
      // 菜单模式：Tab 是"离开菜单"。先把焦点还给触发钮**再让默认行为跑**，浏览器于是从
      // 触发钮继续走到下一个控件；preventDefault 会把 Tab 变成陷阱，那是对话框的语义。
      close();
      return;
    }
    const items = itemsOf(panel.current);
    if (!items.length) return;
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    let next = -1;
    if (event.key === 'ArrowDown') next = (at + 1) % items.length;
    else if (event.key === 'ArrowUp') next = (at - 1 + items.length) % items.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = items.length - 1;
    if (next < 0) return;
    event.preventDefault();
    items[next]?.focus();
  };

  const current = OPTIONS[theme];

  return (
    <div className="theme-menu" ref={root}>
      <button
        className="icon-button"
        type="button"
        id="theme-toggle"
        ref={trigger}
        aria-haspopup="menu"
        aria-expanded={open}
        // 名字里带当前档位：纯图标钮的 aria-label 是屏幕阅读器唯一的信息来源，而"主题"
        // 两个字说不出现在是哪一档。title 同理——鼠标用户也读得到。
        aria-label={`主题：${current.label}`}
        title={`主题：${current.label}`}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name={current.icon} />
      </button>
      <div
        className="theme-menu__panel"
        ref={panel}
        hidden={!open}
        role="menu"
        aria-label="主题"
        onKeyDown={onKeyDown}
      >
        {THEMES.map((value) => (
          <button
            key={value}
            className="theme-menu__item"
            type="button"
            role="menuitemradio"
            aria-checked={value === theme}
            onClick={() => pick(value)}
          >
            <Icon name={OPTIONS[value].icon} />
            <span className="theme-menu__label">{OPTIONS[value].label}</span>
            <span className="theme-menu__check">
              {value === theme ? <Icon name="check" /> : null}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
