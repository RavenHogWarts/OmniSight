// 四种状态的构造器（06 文档 §10.1）。**它们必须长得不一样**，这就是本文件存在的理由：
//
//   加载中（首次）  骨架屏，形状与真实内容一致
//   加载中（刷新）  保留旧数据 + 卡片顶沿细进度条（CSS 的 data-refreshing）
//   无数据（正常）  "这一天没有记录" + 跳到最近有数据的日期
//   加载失败        具体原因 + 重试按钮
//   能力不可用      面板内说明块，**不给重试按钮**——重试不会改变结果
//
// 最后两种最容易被合并成一种，而合并的后果是用户在 Wayland 上看到"这一天没有记录"
// 然后去排查自己的使用习惯。
import { h } from '../core/dom.js';

/**
 * @param {string} [kind]
 * @param {number} [count]
 */
export function skeleton(kind = 'text', count = 1) {
  const nodes = [];
  for (let index = 0; index < count; index += 1) {
    nodes.push(h('div', { class: `skeleton skeleton--${kind}` }));
  }
  return nodes.length === 1 ? nodes[0] : h('div', null, ...nodes);
}

/** @param {number} [count] */
export function skeletonRows(count = 5) {
  return h('div', null, ...Array.from({ length: count }, () => h('div', { class: 'skeleton skeleton--row' })));
}

/**
 * `mark` \u65e2\u63a5\u53d7\u4e00\u4e2a\u5b57\u7b26\uff08\u9ed8\u8ba4\u7684 \u25cb\uff09\uff0c\u4e5f\u63a5\u53d7\u4e00\u4e2a\u8282\u70b9\u2014\u2014\u7a7a\u6001\u56fe\u6807\u73b0\u5728\u662f\u5185\u8054 SVG\uff0c
 * \u4e0e\u5168\u7ad9\u4e00\u81f4\uff0814 \u6587\u6863 \u00a73.5\uff09\u3002
 * @param {{ title: string, detail?: string, mark?: import('../types/dom.js').Child,
 *           action?: import('../types/dom.js').Child }} options
 */
export function emptyState({ title, detail = '', mark = '\u25cb', action = null }) {
  return h(
    'div',
    { class: 'empty' },
    typeof mark === 'string'
      ? h('div', { class: 'empty__mark', attrs: { 'aria-hidden': 'true' }, text: mark })
      : h('div', { class: 'empty__mark', attrs: { 'aria-hidden': 'true' } }, mark),
    h('div', { class: 'empty__title', text: title }),
    detail ? h('div', { class: 'empty__detail', text: detail }) : null,
    action,
  );
}

/**
 * @param {{ message?: string, onRetry?: (() => void) | null }} options
 */
export function errorState({ message, onRetry = null }) {
  return h(
    'div',
    { class: 'empty empty--error', attrs: { role: 'alert' } },
    h('div', { class: 'empty__mark', attrs: { 'aria-hidden': 'true' }, text: '\u26a0' }),
    h('div', { class: 'empty__title', text: '加载失败' }),
    h('div', { class: 'empty__detail', text: message || '未知错误' }),
    onRetry
      ? h('button', { class: 'button', type: 'button', text: '重试', on: { click: onRetry } })
      : null,
  );
}

/**
 * 面板内的能力说明块（06 文档 §4.2 第二级）。
 *
 * 文案的三段（缺什么 / 什么仍然正常 / 怎么解决）由**后端**给：
 * degraded[].title / .detail / .hint。前端不编文案，也不判断平台——
 * 否则每加一个平台都要改前端（07 文档 §10 第 4 行）。
 */
/**
 * @param {{ title: string, detail?: string, hint?: string }} options
 */
export function capabilityNotice({ title, detail = '', hint = '' }) {
  return h(
    'div',
    { class: 'notice', attrs: { role: 'note' } },
    h('span', { class: 'notice__mark', attrs: { 'aria-hidden': 'true' }, text: 'i' }),
    h(
      'div',
      null,
      h('div', { class: 'notice__title', text: title }),
      detail ? h('div', { class: 'notice__detail', text: detail }) : null,
      hint ? h('div', { class: 'notice__hint', text: hint }) : null,
    ),
  );
}

/** 数据缺口的图例注记。图表里画斜纹，图例里说明斜纹是什么意思。 */
/** @param {number} count */
export function gapLegend(count) {
  if (!count) return null;
  return h(
    'div',
    { class: 'heat-legend' },
    h('span', { class: 'heat-legend__step hatched', attrs: { 'aria-hidden': 'true' } }),
    h('span', { text: `${count} 天没有采集记录（斜纹），不是零` }),
  );
}
