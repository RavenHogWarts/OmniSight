// 周期栏（06 文档 §4.1）。**在所有视图间共享状态**——从总览切到键盘时选中的日期不变。
// 这是旧版两个应用最割裂的地方：各自维护独立的日期状态，切换程序等于重新选一次日期。
import { h, mount, setText } from '../core/dom.js';
import { getState, setState, subscribe } from '../core/store.js';
import { RANGES } from '../domain/metrics.js';
import { canGoForward, isPageable, shift, todayISO } from '../domain/period.js';
import { segmented } from './controls.js';

export function mountPeriodNav(container) {
  const prev = h('button', {
    class: 'icon-button', type: 'button', text: '\u2039',
    attrs: { 'aria-label': '上一个周期' },
    on: { click: () => step(-1) },
  });
  const next = h('button', {
    class: 'icon-button', type: 'button', text: '\u203a',
    attrs: { 'aria-label': '下一个周期' },
    on: { click: () => step(1) },
  });
  const label = h('div', { class: 'period-label', attrs: { 'aria-live': 'polite' } });
  const today = h('button', {
    class: 'button', type: 'button', text: '今天',
    on: { click: () => setState('period', { ...getState().period, date: todayISO() }) },
  });

  const ranges = segmented(
    RANGES,
    getState().period.range,
    (id) => pickRange(id),
    { label: '时间范围' },
  );

  const startInput = h('input', { type: 'date', class: 'control', attrs: { 'aria-label': '起始日期' } });
  const endInput = h('input', { type: 'date', class: 'control', attrs: { 'aria-label': '结束日期' } });
  const custom = h(
    'div',
    { class: 'period-custom', hidden: true },
    startInput,
    h('span', { text: '\u2013' }),
    endInput,
  );
  const applyCustom = () => {
    if (!startInput.value || !endInput.value) return;
    setState('period', { range: 'custom', date: null, start: startInput.value, end: endInput.value });
  };
  startInput.addEventListener('change', applyCustom);
  endInput.addEventListener('change', applyCustom);

  mount(
    container,
    h('div', { class: 'periodbar__nav' }, prev, label, next),
    today,
    h('span', { class: 'spacer' }),
    custom,
    ranges.root,
  );

  const render = () => {
    const { period, periodMeta } = getState();
    ranges.setActive(period.range);
    const pageable = isPageable(period.range);
    prev.disabled = !pageable;
    next.disabled = !pageable || !canGoForward(period.range, anchorOf(), todayISO());
    today.hidden = period.range === 'total' || Boolean(periodMeta?.is_current);
    custom.hidden = period.range !== 'custom';
    // 标题一律用后端给的 label：前端不会算"9月2日 周三"里的星期，也不该算。
    setText(label, periodMeta?.label || '\u2026');
  };

  subscribe('period', render);
  subscribe('periodMeta', render);
  render();

  return { render, step, pickRange };
}

/** 锚点优先用后端规整过的值，否则退回本地选择。 */
function anchorOf() {
  const { period, periodMeta } = getState();
  return periodMeta?.anchor || period.date || todayISO();
}

export function step(direction) {
  const { period } = getState();
  if (!isPageable(period.range)) return;
  if (direction > 0 && !canGoForward(period.range, anchorOf(), todayISO())) return;
  setState('period', { ...period, date: shift(period.range, anchorOf(), direction) });
}

export function pickRange(id) {
  const { period, periodMeta } = getState();
  if (id === 'custom') {
    const end = periodMeta?.truncated_end || todayISO();
    const start = periodMeta?.start || end;
    setState('period', { range: 'custom', date: null, start, end });
    return;
  }
  setState('period', { range: id, date: anchorOf(), start: null, end: null });
}

export function goToday() {
  setState('period', { ...getState().period, date: todayISO() });
}
