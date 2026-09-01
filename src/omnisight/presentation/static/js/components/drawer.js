// 抽屉：焦点陷阱 + Esc 关闭 + 归还焦点（06 文档 §13）。
//
// 焦点陷阱不是装饰：抽屉打开后 Tab 键若能走到底下的页面，键盘用户会"掉出"抽屉且
// 看不到自己在哪。归还焦点同理——关掉抽屉后焦点必须回到打开它的那个按钮。
import { h } from '../core/dom.js';

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea, [tabindex]:not([tabindex="-1"])';

let openDrawer = null;

export function drawer({ title, body, footer = null, onClose = null }) {
  if (openDrawer) openDrawer.close();
  const opener = document.activeElement;
  const host = document.getElementById('overlays');

  const closeButton = h('button', {
    class: 'icon-button', type: 'button', text: '\u2715',
    attrs: { 'aria-label': '关闭' },
  });
  const panel = h(
    'aside',
    { class: 'drawer', attrs: { role: 'dialog', 'aria-modal': 'true', 'aria-label': title } },
    h('div', { class: 'drawer__head' }, h('h2', { text: title }), h('span', { class: 'spacer' }), closeButton),
    h('div', { class: 'drawer__body' }, body),
    footer ? h('div', { class: 'drawer__foot' }, footer) : null,
  );
  const scrim = h('div', { class: 'scrim' });

  const close = () => {
    document.removeEventListener('keydown', onKeydown, true);
    scrim.remove();
    panel.remove();
    openDrawer = null;
    if (onClose) onClose();
    if (opener && typeof opener.focus === 'function') opener.focus();
  };

  function onKeydown(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== 'Tab') return;
    const items = [...panel.querySelectorAll(FOCUSABLE)].filter((node) => node.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    } else if (!panel.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    }
  }

  closeButton.addEventListener('click', close);
  scrim.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown, true);
  host.append(scrim, panel);
  closeButton.focus();

  openDrawer = { close, panel };
  return openDrawer;
}

export function closeDrawer() {
  if (openDrawer) openDrawer.close();
}
