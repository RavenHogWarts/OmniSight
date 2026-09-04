// 分段控件与胶囊。**一套控件服务三个用途**（周期范围、指标、时间粒度）——
// 原 KeyTrace 的"视图切换 + 范围分段 + 指标切换"三层各有一套样式（06 文档 §4）。
import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icon.tsx';

export interface SegmentedItem {
  id: string;
  name: string;
  title?: string;
}

/**
 * 用 aria-pressed 而不是 class 表达选中态：屏幕阅读器因此不需要额外的文案。
 */
export function Segmented({
  items,
  active,
  onPick,
  small = false,
  label = '',
}: {
  items: readonly SegmentedItem[];
  active: string;
  onPick: (id: string) => void;
  small?: boolean;
  label?: string;
}) {
  return (
    <div
      className={small ? 'segmented segmented--sm' : 'segmented'}
      role="group"
      aria-label={label}
    >
      {items.map((item) => (
        <button
          key={item.id}
          className="segmented__item"
          type="button"
          aria-pressed={item.id === active}
          title={item.title || item.name}
          onClick={() => onPick(item.id)}
        >
          {item.name}
        </button>
      ))}
    </div>
  );
}

/** 单个可切换胶囊（分类过滤用）。 */
export function Chip({
  item,
  active,
  onPick,
}: {
  item: SegmentedItem;
  active: boolean;
  onPick: (id: string) => void;
}) {
  return (
    <button className="chip" type="button" aria-pressed={active} onClick={() => onPick(item.id)}>
      {item.name}
    </button>
  );
}

/**
 * 搜索框。**去抖 220ms**：每敲一个字母就发一次请求会让 300 个应用的库明显卡顿。
 *
 * 输入值是受控的本地 state，而向上抛出的是去抖后的值——这样打字不卡，而请求不多。
 */
export function SearchBox({
  placeholder = '搜索',
  value = '',
  onInput,
}: {
  placeholder?: string;
  value?: string;
  onInput: (value: string) => void;
}) {
  const [text, setText] = useState(value);
  const timer = useRef(0);
  // onInput 放进 ref：它通常是视图里的内联箭头函数，每次渲染都是新的引用，
  // 直接进 effect 的依赖会让去抖计时器每次渲染都重置。
  const handler = useRef(onInput);
  handler.current = onInput;

  useEffect(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => handler.current(text.trim()), 220);
    return () => window.clearTimeout(timer.current);
  }, [text]);

  return (
    <label className="search">
      <span className="search__mark" aria-hidden="true">
        <Icon name="search" />
      </span>
      <input
        type="search"
        value={text}
        placeholder={placeholder}
        aria-label={placeholder}
        enterKeyHint="search"
        onChange={(event) => setText(event.target.value)}
      />
    </label>
  );
}

export function Checkbox({
  label,
  checked = false,
  onChange,
}: {
  label: string;
  checked?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="checkbox">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function Switch({
  checked = false,
  disabled = false,
  onChange,
  label = '',
}: {
  checked?: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
}) {
  return (
    <span className="switch">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        aria-label={label}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch__track" />
    </span>
  );
}
