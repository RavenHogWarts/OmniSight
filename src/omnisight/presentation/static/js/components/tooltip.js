// 单例浮动提示（06 文档 §10）。canvas 没有 DOM 节点，命中检测在图表里做，
// 这里只负责定位与内容——现状柱状图完全没有 tooltip，只能看轮廓。
import { h, mount } from '../core/dom.js';

let node = null;

function ensure() {
  if (node) return node;
  node = h('div', { class: 'tooltip', attrs: { role: 'tooltip', 'aria-hidden': 'true' } });
  document.body.append(node);
  return node;
}

/** rows: [[label, value]]；note 用于"该日无应用归因"这类说明（06 文档 §4.2 第三级）。 */
export function show({ title, rows = [], note = '', x = 0, y = 0 }) {
  const tip = ensure();
  mount(
    tip,
    title ? h('div', { class: 'tooltip__title', text: title }) : null,
    ...rows.map(([label, value]) =>
      h('div', { class: 'tooltip__row' }, h('span', { text: label }), h('span', { text: String(value) })),
    ),
    note ? h('div', { class: 'tooltip__note', text: note }) : null,
  );
  tip.dataset.open = 'true';
  place(tip, x, y);
}

export function hide() {
  if (node) node.dataset.open = 'false';
}

/** 靠近视口边界时翻转，而不是被裁掉。 */
function place(tip, x, y) {
  const rect = tip.getBoundingClientRect();
  const margin = 12;
  let left = x + margin;
  let top = y + margin;
  if (left + rect.width > window.innerWidth - margin) left = x - rect.width - margin;
  if (top + rect.height > window.innerHeight - margin) top = y - rect.height - margin;
  tip.style.setProperty('left', `${Math.max(margin, left)}px`);
  tip.style.setProperty('top', `${Math.max(margin, top)}px`);
}
