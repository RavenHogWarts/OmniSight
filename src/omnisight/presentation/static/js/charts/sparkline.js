// 迷你趋势线（14 文档 §2.6）。
//
// 它替换的是 `.metric__bar`——那根条画的是 `min(1, now / max(now, prev))`，只要本期
// 不比上期少就恒为满格，也就是说它不编码任何东西。趋势线画的是**上一档粒度的同周期
// 序列**（看"日"时给最近 12 天，看"周"时给最近 12 周），因此它回答的是指标卡自己
// 回答不了的那个问题：这个数最近是什么走势。
//
// 不用 Chart 底座：这里没有轴、没有命中区、没有 tooltip，一条线加一个端点而已，
// 走 Chart 会白搭一个 ResizeObserver 与一张 sr-only 表（数值已在卡面上）。
import { on as busOn } from '../core/bus.js';
import { h } from '../core/dom.js';
import { cssColor, setupCanvas } from './canvas.js';

/**
 * @param {{ height?: number, accent?: string }} [options]
 */
export function sparkline({ height = 28, accent = '--accent' } = {}) {
  const canvas = h('canvas', {
    class: 'sparkline',
    // 纯装饰：数值与走势描述都在卡面文字里，读屏不需要再读一次这条线。
    attrs: { 'aria-hidden': 'true' },
    style: { height: `${height}px` },
  });
  /** @type {number[]} */
  let points = [];

  const observer = new ResizeObserver(() => render());
  observer.observe(canvas);
  const unsubscribeTheme = busOn('theme:changed', () => render());

  function render() {
    if (points.length < 2) {
      const { ctx, width, height: h2 } = setupCanvas(canvas);
      ctx.clearRect(0, 0, width, h2);
      return;
    }
    const { ctx, width, height: h2 } = setupCanvas(canvas);
    const line = cssColor(accent, '#2f7cf6');
    const faint = cssColor('--text-tertiary', '#6b6b73');
    const pad = 3;
    const plotW = Math.max(1, width - pad * 2);
    const plotH = Math.max(1, h2 - pad * 2);
    const top = Math.max(...points);
    const bottom = Math.min(...points);
    const span = top - bottom || 1;
    const xy = (value, index) => [
      pad + (plotW * index) / (points.length - 1),
      pad + plotH - ((value - bottom) / span) * plotH,
    ];

    // 除当前点外整条线去强调：读者要看的是"走势 + 现在在哪"，不是每一个历史点。
    ctx.strokeStyle = faint;
    ctx.globalAlpha = 0.55;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.beginPath();
    points.forEach((value, index) => {
      const [x, y] = xy(value, index);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.globalAlpha = 1;

    // 端点标记 ≥8px（含 2px 表面色环），否则在 28px 高的线上找不到"现在"。
    const [cx, cy] = xy(points[points.length - 1], points.length - 1);
    ctx.fillStyle = cssColor('--surface-card', '#fff');
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = line;
    ctx.beginPath();
    ctx.arc(cx, cy, 2.5, 0, Math.PI * 2);
    ctx.fill();
  }

  return {
    root: canvas,
    /** @param {readonly number[]} values */
    update(values) {
      points = (values || []).map((value) => Number(value) || 0);
      render();
    },
    destroy() {
      observer.disconnect();
      unsubscribeTheme();
    },
  };
}
