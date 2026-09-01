// 带标题与右上角控件的卡片。四个视图共用，避免每处各写一遍 card__head。
import { h } from '../core/dom.js';

export function card(titleText, body, controls = [], footer = null) {
  return h(
    'section',
    { class: 'card' },
    h(
      'div',
      { class: 'card__head' },
      h('h2', { class: 'card__title', text: titleText }),
      h('span', { class: 'spacer' }),
      ...controls,
    ),
    body,
    footer,
  );
}
