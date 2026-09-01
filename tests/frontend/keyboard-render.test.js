// 键盘渲染器：布局数据 -> DOM。**这是 M3 收益最大的一处改造**（旧 KeyTrace 是 860 行
// 硬编码 HTML，欧洲用户因此一直看着错误的键盘）。
//
// 布局 JSON 直接从后端的 layouts.py 导出（见 tests/unit/test_frontend_js.py 如何生成），
// 因此这些断言验证的是"渲染器能正确吃下真实布局"，不是"渲染器能吃下我编的假数据"。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installDom } from './dom-shim.js';

const restore = installDom();
const { buildKeyboard, keyOrder, keyRows } = await import(
  '../../src/omnisight/presentation/static/js/domain/keyboard-layout.js'
);
const { h, mount, renderKeyed } = await import(
  '../../src/omnisight/presentation/static/js/core/dom.js'
);
const { capabilityNotice, errorState } = await import(
  '../../src/omnisight/presentation/static/js/components/states.js'
);

const LAYOUTS = JSON.parse(readFileSync(new URL('./layouts.json', import.meta.url), 'utf8'));

test.after(() => restore());

for (const family of Object.keys(LAYOUTS)) {
  test(`${family}: 每一行的宽度总和都是 23 单位（键与空隙用同一个公式）`, () => {
    const layout = LAYOUTS[family];
    for (const [index, row] of layout.rows.entries()) {
      const units = row.reduce((sum, slot) => sum + Number(slot.w), 0);
      assert.equal(units, layout.unit_hint.max_units, `第 ${index + 1} 行`);
    }
  });

  test(`${family}: 渲染出的键数与布局里的真实键数一致`, () => {
    const layout = LAYOUTS[family];
    const { root, nodes } = buildKeyboard(layout);
    const expected = layout.rows.flat().filter((slot) => slot.id !== 'gap').length;
    assert.equal(nodes.size, expected);
    assert.equal(root.querySelectorAll('.key-cap').length, expected);
    assert.equal(root.children.length, layout.unit_hint.rows);
    assert.equal(root.dataset.family, family);
  });

  test(`${family}: 每个键都带上 --w / --h 与 data-key-id`, () => {
    const layout = LAYOUTS[family];
    const { nodes } = buildKeyboard(layout);
    for (const row of layout.rows) {
      for (const slot of row) {
        if (slot.id === 'gap') continue;
        const cap = nodes.get(slot.id);
        assert.ok(cap, `缺少 ${slot.id}`);
        assert.equal(cap.dataset.keyId, slot.id);
        assert.equal(cap.style.getPropertyValue('--w'), String(slot.w));
        assert.equal(cap.style.getPropertyValue('--h'), String(slot.h ?? 1));
        // 标签由后端的 keymap.label_for 统一提供，渲染器不自己拼写法。
        assert.equal(cap.querySelector('.key-cap__label').textContent, slot.label);
      }
    }
  });

  test(`${family}: 空隙渲染成占位符，不渲染成键`, () => {
    const layout = LAYOUTS[family];
    const { root, nodes } = buildKeyboard(layout);
    const gaps = layout.rows.flat().filter((slot) => slot.id === 'gap').length;
    assert.equal(root.querySelectorAll('.key-spacer').length, gaps);
    assert.equal(nodes.has('gap'), false);
  });
}

test('ISO 的 L 形回车带 data-shape，ANSI 的回车不带', () => {
  const iso = buildKeyboard(LAYOUTS.iso105).nodes.get('enter');
  assert.equal(iso.dataset.shape, 'iso_enter');
  assert.equal(iso.style.getPropertyValue('--h'), '2');
  const ansi = buildKeyboard(LAYOUTS.ansi104).nodes.get('enter');
  assert.equal(ansi.dataset.shape, undefined);
  assert.equal(ansi.style.getPropertyValue('--h'), '1');
});

test('ISO 有第 102 键（iso_backslash），ANSI 没有', () => {
  assert.equal(buildKeyboard(LAYOUTS.iso105).nodes.has('iso_backslash'), true);
  assert.equal(buildKeyboard(LAYOUTS.ansi104).nodes.has('iso_backslash'), false);
});

test('未知形状退化为矩形键，不抛异常也不吞掉这个键', () => {
  const warnings = [];
  const original = console.warn;
  console.warn = (message) => warnings.push(message);
  try {
    const layout = { family: 'future', name: '未来布局', rows: [[{ id: 'esc', label: 'Esc', w: 1, shape: 'l_shaped_thing' }]] };
    const { nodes } = buildKeyboard(layout);
    const cap = nodes.get('esc');
    assert.ok(cap);
    assert.equal(cap.dataset.shape, undefined);
  } finally {
    console.warn = original;
  }
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /l_shaped_thing/);
});

test('键盘整体是一个 tabstop，单个键不进 Tab 序（07 文档 §9）', () => {
  const { root, nodes } = buildKeyboard(LAYOUTS.ansi104);
  assert.equal(root.getAttribute('tabindex'), '0');
  assert.equal(root.getAttribute('role'), 'group');
  for (const cap of nodes.values()) {
    assert.equal(cap.getAttribute('tabindex'), null);
    assert.equal(cap.getAttribute('role'), 'img');
  }
});

test('keyOrder / keyRows 给方向键导航用，且不含 gap', () => {
  const order = keyOrder(LAYOUTS.ansi104);
  const rows = keyRows(LAYOUTS.ansi104);
  assert.equal(order.includes('gap'), false);
  assert.equal(rows.length, LAYOUTS.ansi104.unit_hint.rows);
  assert.equal(rows.flat().length, order.length);
});

test('h() 走 textContent：窗口标题里的 HTML 只会是字符串', () => {
  // 应用名与窗口标题来自操作系统，任何进程都能把自己的窗口命名成一段 HTML。
  const hostile = '<img src=x onerror=alert(1)>';
  const node = h('span', { text: hostile });
  assert.equal(node.textContent, hostile);
  assert.equal(node.children.length, 0);
});

test('能力说明块不带重试按钮，错误态才带（06 文档 §10.1）', () => {
  const notice = capabilityNotice({ title: '测不到', detail: '别的照常', hint: '换个会话' });
  assert.equal(notice.querySelectorAll('button').length, 0);
  let retried = 0;
  const error = errorState({ message: '库锁了', onRetry: () => { retried += 1; } });
  assert.equal(error.querySelectorAll('button').length, 1);
});

test('renderKeyed 复用节点：图标不会每次刷新都闪一下', () => {
  const host = h('div');
  const create = (item) => h('div', { text: item.name });
  const items = [{ id: 1, name: 'a' }, { id: 2, name: 'b' }];
  renderKeyed(host, items, (item) => item.id, create);
  const first = host.children[0];
  renderKeyed(host, [{ id: 1, name: 'a2' }, { id: 2, name: 'b' }], (item) => item.id, create,
    (node, item) => { node.textContent = item.name; });
  assert.equal(host.children[0], first, '同一个 key 必须复用同一个节点');
  assert.equal(host.children[0].textContent, 'a2');
  // 数据里消失的行要被移除，而不是留在 DOM 里。
  renderKeyed(host, [{ id: 2, name: 'b' }], (item) => item.id, create);
  assert.equal(host.children.length, 1);
  assert.equal(host.children[0].textContent, 'b');
});

test('mount 用 replaceChildren 清空，不用 innerHTML', () => {
  const host = h('div', null, h('span', { text: 'old' }));
  mount(host, h('b', { text: 'new' }));
  assert.equal(host.children.length, 1);
  assert.equal(host.textContent, 'new');
});
