// 指标卡（06 文档 §5.1、14 文档 §2.6/§3.4）。
//
// delta 的箭头**不做价值判断**：屏幕时间上升不一定是坏事，按键增多也不一定好。
// 统一用 --text-secondary，只有方向没有颜色。纯统计工具不该替用户下道德判断。
//
// 解剖来自键帽（14 文档 §3.4）：标签左上、数值右下、1px 描边、**无独立卡头**——标签
// 本身就是卡头。产品自己的器物是键帽，界面的形状语言从它推导，而不是再发明一种卡片。
import { h, setText } from '../core/dom.js';
import { formatDelta } from '../domain/format.js';
import { contextBars } from '../charts/context-bars.js';
import { icon } from './icon.js';
import { skeleton } from './states.js';

/**
 * @param {{ label: string, hint?: string, hero?: boolean, series?: 'time' | 'keys',
 *           metric?: 'seconds' | 'presses', format?: (value: number) => string }} options
 */
export function statCard({
  label,
  hint = '',
  hero = false,
  series = 'time',
  metric = 'seconds',
  format = (value) => String(value),
}) {
  // 大号独立数字用**比例数字**：44px 上的 tabular-nums 会让 121 这类数字看起来松散。
  // tabular-nums 留给需要竖向对齐的列（14 文档 §3.3）。
  const value = h('div', { class: 'metric__value', text: '—' });
  const delta = h('div', { class: 'metric__delta numeric' });
  // 卡上那条迷你图是**对照条**，不是本周期内部的走势线：后者与卡上方的活动带同源
  // （overview.js 的注释早就写明了这一点），因此画两遍只是把同一件事说两次，
  // 而"这段时间算不算多"仍然没人回答（14 文档 §2.18）。
  const contextHost = h('div', { class: 'metric__context' });
  const context = contextBars(contextHost, { accent: series, metric, format, label: `${label}对照条` });
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
    contextHost,
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
      context.update({ buckets: [], current: '' });
      contextHost.hidden = true;
    },
    /**
     * `contextSeries` 是 `/overview` 的 `context` 段：当前周期所在的上一档粒度序列
     * （日→近 7 天、周→近 8 周、月→近 12 个月、年→全部年份）。
     *
     * `range=total` 与 `custom` 没有可比的序列，后端整段不给——那时整块隐藏，
     * 而不是画一根孤零零的柱子充数（14 文档 §4.3）。
     *
     * @param {{ text: string, deltaValue?: import('../types/api.js').Delta | null,
     *           contextSeries?: import('../types/api.js').ContextSeries | null,
     *           footnote?: string }} options
     */
    update({ text, deltaValue = null, contextSeries = null, footnote = '' }) {
      value.replaceChildren(document.createTextNode(text));
      setText(delta, deltaValue ? formatDelta(deltaValue) : '');
      const buckets = (contextSeries && contextSeries.buckets) || [];
      contextHost.hidden = buckets.length === 0;
      context.update({ buckets, current: (contextSeries && contextSeries.current) || '' });
      setText(foot, footnote);
    },
    destroy() {
      context.destroy();
    },
  };
}
