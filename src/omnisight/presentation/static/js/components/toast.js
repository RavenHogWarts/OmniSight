// 操作反馈。写操作（改别名、改分类、改设置）的唯一成功/失败通道。
import { h } from '../core/dom.js';

const LIFETIME_MS = 4200;
let host = null;

function ensure() {
  if (!host) host = document.getElementById('toasts');
  return host;
}

export function toast(message, kind = 'info') {
  const target = ensure();
  if (!target) return;
  const node = h(
    'div',
    { class: 'toast', dataset: { kind }, attrs: { role: kind === 'error' ? 'alert' : 'status' } },
    h('span', { class: 'toast__dot', attrs: { 'aria-hidden': 'true' } }),
    h('span', { text: message }),
  );
  target.append(node);
  window.setTimeout(() => node.remove(), LIFETIME_MS);
}

export const ok = (message) => toast(message, 'ok');
export const fail = (message) => toast(message, 'error');
