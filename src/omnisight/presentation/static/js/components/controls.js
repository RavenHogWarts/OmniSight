// 分段控件与胶囊。**一套控件服务三个用途**（周期范围、指标、时间粒度）——
// 原 KeyTrace 的"视图切换 + 范围分段 + 指标切换"三层各有一套样式（06 文档 §4）。
import { h } from '../core/dom.js';

/**
 * items: [{id, name, title}]；返回 { root, setActive }。
 * 用 aria-pressed 而不是 class 表达选中态：屏幕阅读器因此不需要额外的文案。
 */
export function segmented(items, active, onPick, { small = false, label = '' } = {}) {
  const buttons = new Map();
  const root = h('div', {
    class: small ? 'segmented segmented--sm' : 'segmented',
    attrs: { role: 'group', 'aria-label': label },
  });
  for (const item of items) {
    const button = h('button', {
      class: 'segmented__item',
      type: 'button',
      text: item.name,
      attrs: { 'aria-pressed': String(item.id === active), title: item.title || item.name },
      on: { click: () => onPick(item.id) },
    });
    buttons.set(item.id, button);
    root.append(button);
  }
  return {
    root,
    setActive(next) {
      for (const [id, button] of buttons) button.setAttribute('aria-pressed', String(id === next));
    },
  };
}

/** 单个可切换胶囊（分类过滤用）。 */
export function chip(item, active, onPick) {
  return h('button', {
    class: 'chip',
    type: 'button',
    text: item.name,
    attrs: { 'aria-pressed': String(active) },
    on: { click: () => onPick(item.id) },
  });
}

export function searchBox({ placeholder = '搜索', value = '', onInput }) {
  const input = h('input', {
    type: 'search',
    value,
    attrs: { placeholder, 'aria-label': placeholder, enterkeyhint: 'search' },
  });
  let timer = 0;
  input.addEventListener('input', () => {
    window.clearTimeout(timer);
    // 去抖：每敲一个字母就发一次请求会让 300 个应用的库明显卡顿。
    timer = window.setTimeout(() => onInput(input.value.trim()), 220);
  });
  const root = h(
    'label',
    { class: 'search' },
    h('span', { class: 'search__mark', attrs: { 'aria-hidden': 'true' }, text: '\u2315' }),
    input,
  );
  return { root, input };
}

export function checkbox({ label, checked = false, onChange }) {
  const input = h('input', { type: 'checkbox', checked });
  input.addEventListener('change', () => onChange(input.checked));
  return h('label', { class: 'checkbox' }, input, h('span', { text: label }));
}

export function switchControl({ checked = false, disabled = false, onChange, label = '' }) {
  const input = h('input', {
    type: 'checkbox',
    checked,
    disabled,
    attrs: { 'aria-label': label },
  });
  input.addEventListener('change', () => onChange(input.checked));
  const root = h('span', { class: 'switch' }, input, h('span', { class: 'switch__track' }));
  return { root, input };
}
