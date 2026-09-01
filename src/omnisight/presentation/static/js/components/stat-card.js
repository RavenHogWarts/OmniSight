// 指标卡（06 文档 §5.1）。
//
// delta 的箭头**不做价值判断**：屏幕时间上升不一定是坏事，按键增多也不一定好。
// 统一用 --text-secondary，只有方向没有颜色。纯统计工具不该替用户下道德判断。
import { h, setText, setVar } from '../core/dom.js';
import { formatDelta } from '../domain/format.js';
import { skeleton } from './states.js';

export function statCard({ label, hint = '' }) {
  const value = h('div', { class: 'metric__value numeric', text: '\u2014' });
  const delta = h('div', { class: 'metric__delta numeric' });
  const bar = h('div', { class: 'metric__bar' }, h('i'));
  const foot = h('div', { class: 'metric__foot' });
  const body = h(
    'div',
    null,
    h(
      'div',
      { class: 'metric__label' },
      h('span', { text: label }),
      hint ? h('span', { class: 'card__hint', attrs: { title: hint }, text: '\u24d8' }) : null,
    ),
    h('div', { class: 'metric__row' }, value, delta),
    bar,
    foot,
  );
  const root = h('div', { class: 'card' }, body);

  return {
    root,
    loading() {
      setText(value, '');
      value.replaceChildren(skeleton('value'));
      setText(foot, '');
      setText(delta, '');
    },
    /** ratio: 与对比周期的相对量（0..1），只用于那根对比条。 */
    update({ text, deltaValue = null, ratio = 0, footnote = '' }) {
      value.replaceChildren(document.createTextNode(text));
      setText(delta, deltaValue ? formatDelta(deltaValue) : '');
      setVar(bar, '--fill', Math.max(0, Math.min(1, ratio)));
      setText(foot, footnote);
    },
  };
}

/** 一行"名称 + 条 + 数值"，类别列表与强度分布共用。 */
export function meterRow({ name, category = null, profile = null }) {
  const bar = h('div', { class: 'bar' }, h('i'));
  const value = h('span', { class: 'intensity__value numeric' });
  const root = h(
    'div',
    {
      class: 'intensity__row',
      dataset: { ...(category ? { category } : {}), ...(profile ? { profile } : {}) },
    },
    h('span', { class: 'intensity__name', text: name }),
    bar,
    value,
  );
  return {
    root,
    update(ratio, text) {
      setVar(bar, '--fill', Math.max(0, Math.min(1, ratio)));
      setText(value, text);
    },
  };
}
