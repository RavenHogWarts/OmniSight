// 服务端下发布局的**渲染器**。这里没有一个坐标（07 文档 §6.4、06 文档 §7.1）。
//
// 旧 KeyTrace 把 104 个键的 DOM 硬编码在 HTML 里，键定义还与 Python 的 keys.py 重复
// 了一份。改成数据驱动之后：加/改键位只改后端；ISO 105 与 ANSI 104 只是同一个渲染器的
// 两份输入；"两份清单比对"这种脆弱机制不再需要——因为只有一份数据。
//
// 三条约束（对应 06 文档 §7.1 的三条）：
//   1. 不写死行数与每行键数，只遍历 rows。
//   2. 未知 shape 退化为矩形键并 console.warn，绝不抛异常——后端加了新形状时
//      旧前端应该还能用，只是那个键画成方的。
//   3. orphan_keys 由调用方渲染在键盘下方（见 components/keyboard-view.js）。
import { h } from '../core/dom.js';

/** 已知的特殊形状。只有一个，且这就是重点。 */
const KNOWN_SHAPES = new Set(['iso_enter']);
const GAP = 'gap';

/**
 * 布局数据 -> DOM。返回 `{ root, nodes }`，`nodes` 是 key_id -> 键面元素，
 * 供着色与按压动画按 id 直接命中，不必每次查询 DOM。
 */
export function buildKeyboard(layout, { onKeyEnter, onKeyLeave, onKeyActivate } = {}) {
  const nodes = new Map();
  const root = h('div', {
    class: 'keyboard',
    dataset: { family: layout?.family || 'unknown' },
    attrs: {
      role: 'group',
      'aria-label': `键盘热力图（${layout?.name || '未知布局'}）`,
      tabindex: '0',
    },
  });

  for (const row of layout?.rows || []) {
    const rowEl = h('div', { class: 'keyboard__row' });
    for (const slot of row) {
      if (!slot || slot.id === GAP) {
        rowEl.append(spacer(slot?.w ?? 1));
        continue;
      }
      const cap = keyCap(slot);
      nodes.set(slot.id, cap);
      rowEl.append(cap);
    }
    root.append(rowEl);
  }

  if (onKeyEnter) {
    root.addEventListener('pointerover', (event) => {
      const cap = event.target.closest('.key-cap');
      if (cap?.dataset.keyId) onKeyEnter(cap.dataset.keyId, cap, event);
    });
  }
  if (onKeyLeave) {
    root.addEventListener('pointerout', (event) => {
      const cap = event.target.closest('.key-cap');
      if (cap?.dataset.keyId) onKeyLeave(cap.dataset.keyId, cap, event);
    });
  }
  if (onKeyActivate) {
    root.addEventListener('click', (event) => {
      const cap = event.target.closest('.key-cap');
      if (cap?.dataset.keyId) onKeyActivate(cap.dataset.keyId, cap, event);
    });
  }

  return { root, nodes };
}

function spacer(width) {
  const node = h('span', { class: 'key-spacer', attrs: { 'aria-hidden': 'true' } });
  node.style.setProperty('--w', String(width ?? 1));
  return node;
}

function keyCap(slot) {
  const shape = slot.shape && KNOWN_SHAPES.has(slot.shape) ? slot.shape : null;
  if (slot.shape && !shape) {
    // 后端加了本前端不认识的形状。画成矩形仍然可用，但要留下痕迹。
    console.warn(`未知键形 ${slot.shape}（${slot.id}），按矩形渲染`);
  }
  // role="img" 而不是 button：104 个键全进 Tab 序会淹没导航，整块键盘是一个
  // tabstop，方向键在键位间移动（07 文档 §9）。
  const cap = h(
    'div',
    {
      class: 'key-cap',
      dataset: { keyId: slot.id, level: '0', ...(shape ? { shape } : {}) },
      attrs: { role: 'img', 'aria-label': slot.label || slot.id, id: `key-${slot.id}` },
    },
    h('span', { class: 'key-cap__label', text: slot.label || slot.id }),
    h('span', { class: 'key-cap__value', text: '' }),
  );
  cap.style.setProperty('--w', String(slot.w ?? 1));
  cap.style.setProperty('--h', String(slot.h ?? 1));
  return cap;
}

/** 布局里所有真实键的 id（不含 gap），顺序即视觉顺序——方向键导航用它。 */
export function keyOrder(layout) {
  const ids = [];
  for (const row of layout?.rows || []) {
    for (const slot of row) {
      if (slot && slot.id !== GAP) ids.push(slot.id);
    }
  }
  return ids;
}

/** 按行分组的 id，供上下方向键在行间移动。 */
export function keyRows(layout) {
  return (layout?.rows || []).map((row) => row.filter((slot) => slot && slot.id !== GAP).map((slot) => slot.id));
}
