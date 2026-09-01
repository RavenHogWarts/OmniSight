// 降级表达的第一级：全局横幅（06 文档 §4.2）。
//
// 三条规则在这里体现两条：
//   - 文案三段全部来自后端 degraded[]（title/detail/hint），前端不编。
//   - 关闭状态记在 localStorage，**能力恢复后重新出现**：记的是那一条的 code，
//     而不是"用户关过横幅"这一个布尔值。否则用户关掉键盘降级提示之后，
//     下次换成完全不同的一条降级也不会显示。
//
// severity == error 才上横幅。warning 一级留给面板内说明块与图表斜纹，
// 全都做成横幅会让首期 Windows 上的用户被三条黄条挡住半个屏幕。
import { h, mount } from '../core/dom.js';
import { subscribe } from '../core/store.js';

const DISMISS_KEY = 'omnisight.dismissed';

function dismissed() {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch (error) {
    return new Set();
  }
}

function remember(code) {
  const codes = dismissed();
  codes.add(code);
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify([...codes]));
  } catch (error) {
    // 关不掉就下次还显示，比崩掉好。
  }
}

export function mountBanners(container) {
  const render = (notices) => {
    const hidden = dismissed();
    const shown = (notices || []).filter(
      (notice) => notice.severity === 'error' && !hidden.has(notice.code || notice.title),
    );
    if (!shown.length) {
      mount(container);
      return;
    }
    mount(
      container,
      ...shown.map((notice) => banner(notice, () => {
        remember(notice.code || notice.title);
        render(notices);
      })),
    );
  };
  subscribe('degraded', render);
  render([]);
  return render;
}

function banner(notice, onClose) {
  return h(
    'div',
    { class: 'banner', dataset: { severity: notice.severity || 'warning' }, attrs: { role: 'alert' } },
    h('span', { class: 'banner__mark', attrs: { 'aria-hidden': 'true' }, text: '\u26a0' }),
    h(
      'div',
      { class: 'banner__body' },
      h('div', { class: 'banner__title', text: notice.title || '能力受限' }),
      notice.detail ? h('div', { class: 'banner__detail', text: notice.detail }) : null,
      notice.hint ? h('div', { class: 'banner__hint', text: notice.hint }) : null,
    ),
    h('button', {
      class: 'banner__close',
      type: 'button',
      text: '\u2715',
      attrs: { 'aria-label': '关闭提示' },
      on: { click: onClose },
    }),
  );
}

/** 面板问"我依赖的能力在不在"。**只读布尔值，不读 platform.id**（07 文档 §10）。 */
export function capabilityOf(capabilities, name) {
  if (!capabilities) return true;   // 尚未探明：先按可用渲染，status 到位后再降级
  return capabilities[name] !== false;
}

/** 找出与某个能力相关的那条 degraded 说明，好把后端文案原样显示在面板里。 */
export function noticeFor(degraded, capability) {
  return (degraded || []).find((notice) => notice.capability === capability || notice.code === capability) || null;
}
