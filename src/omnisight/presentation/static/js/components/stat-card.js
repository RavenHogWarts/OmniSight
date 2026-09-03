// 指标卡（06 文档 §5.1、14 文档 §2.6/§3.4）。
//
// delta 的箭头**不做价值判断**：屏幕时间上升不一定是坏事，按键增多也不一定好。
// 统一用 --text-secondary，只有方向没有颜色。纯统计工具不该替用户下道德判断。
//
// 解剖来自键帽（14 文档 §3.4）：标签左上、数值右下、1px 描边、**无独立卡头**——标签
// 本身就是卡头。产品自己的器物是键帽，界面的形状语言从它推导，而不是再发明一种卡片。
import { h, setText } from '../core/dom.js';
import { formatDelta } from '../domain/format.js';
import { sparkline } from '../charts/sparkline.js';
import { icon } from './icon.js';
import { skeleton } from './states.js';

/**
 * @param {{ label: string, hint?: string, hero?: boolean, trendColor?: string }} options
 */
export function statCard({ label, hint = '', hero = false, trendColor = '--accent' }) {
  // 大号独立数字用**比例数字**：44px 上的 tabular-nums 会让 121 这类数字看起来松散。
  // tabular-nums 留给需要竖向对齐的列（14 文档 §3.3）。
  const value = h('div', { class: 'metric__value', text: '—' });
  const delta = h('div', { class: 'metric__delta numeric' });
  const trend = sparkline({ accent: trendColor });
  const foot = h('div', { class: 'metric__foot' });
  const root = h(
    'div',
    { class: 'card card--keycap metric', dataset: hero ? { hero: 'true' } : {} },
    h(
      'div',
      { class: 'metric__label' },
      h('span', { text: label }),
      hint
        ? h('span', { class: 'card__hint', attrs: { title: hint, 'aria-label': hint } }, icon('info'))
        : null,
      delta,
    ),
    trend.root,
    value,
    foot,
  );

  return {
    root,
    loading() {
      setText(value, '');
      value.replaceChildren(skeleton('value'));
      setText(foot, '');
      setText(delta, '');
      trend.update([]);
    },
    /**
     * trend: 上一档粒度的同周期序列，画成迷你趋势线。
     * 它替换的是原来那根"对比条"——那根条画的是 min(1, now/max(now, prev))，
     * 只要本期不比上期少就恒为满格，也就是说它不编码任何东西（14 文档 §2.6）。
     */
    update({ text, deltaValue = null, trend: series = null, footnote = '' }) {
      value.replaceChildren(document.createTextNode(text));
      setText(delta, deltaValue ? formatDelta(deltaValue) : '');
      trend.update(series || []);
      setText(foot, footnote);
    },
    destroy() {
      trend.destroy();
    },
  };
}
