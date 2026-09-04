// 每小时应用图标带（16 文档 §A1）。
//
// 结构性验证：24 行是否都在、图标序是否按时长、`+N` 是否与"装不下的 + 后端 top 之外
// 的"两者之和一致、整块缺口是否换成斜纹块而不是画一片 0。视觉层面（是否真的一屏放得
// 下、图标是否清晰）这里测不了，靠人工验收。
import assert from 'node:assert/strict';
import test from 'node:test';
import { installDom } from './dom-shim.js';

const restore = installDom();
const { hourBand } = await import(
  '../../src/omnisight/presentation/static/js/components/hour-band.js'
);
const { h } = await import('../../src/omnisight/presentation/static/js/core/dom.js');

test.after(() => restore());

function app(id, name, seconds, extra = {}) {
  return { app_id: id, display_name: name, seconds, percent: 0, icon_url: `/api/v1/apps/${id}/icon`, ...extra };
}

function hour(value, apps, other = 0) {
  return {
    hour: value,
    total_seconds: apps.reduce((sum, item) => sum + item.seconds, 0) + other,
    categories: {},
    apps,
    other_seconds: other,
    presses: 0,
  };
}

function bandWith(hours, options = {}) {
  const host = h('div');
  const band = hourBand(host);
  band.update({ hours, ...options });
  return { host, band, root: host.children[0] };
}

test('24 行固定在场，没有数据的小时也留一行', () => {
  const { root } = bandWith([hour(10, [app(1, 'Code', 600)])]);
  assert.equal(root.children.length, 24);
  const labels = root.children.map((row) => row.children[0].textContent);
  assert.equal(labels[0], '00:00');
  assert.equal(labels[23], '23:00');
  assert.equal(root.children[3].dataset.empty, 'true');
  assert.equal(root.children[10].dataset.empty, 'false');
});

test('图标按时长倒序，与后端给的顺序无关', () => {
  const { root } = bandWith([hour(9, [app(1, 'Code', 120), app(2, 'Chrome', 900), app(3, 'Kugou', 300)])]);
  const names = root.children[9].children[1].children.map((cell) => cell.dataset.tipTitle);
  assert.deepEqual(names, ['Chrome', 'Kugou', 'Code']);
});

test('`+N` 把装不下的与 other_seconds 合成一格，时长是两者之和', () => {
  // 兜底容量是 8（量不到宽度时），所以 10 个应用会折 2 个，再加 other 一格 = +3。
  const many = Array.from({ length: 10 }, (_, index) => app(index + 1, `App${index + 1}`, 100 - index));
  const { root } = bandWith([hour(14, many, 45)]);
  const cells = root.children[14].children[1].children;
  const more = cells[cells.length - 1];
  assert.equal(more.textContent, '+3');
  // 被折叠的两个是最短的两个（92 + 91），加上 other 的 45 秒 = 228 秒。
  assert.equal(more.dataset.tipDuration, '3m');
});

test('没有溢出时不出现 `+N`', () => {
  const { root } = bandWith([hour(8, [app(1, 'Code', 600)])]);
  const cells = root.children[8].children[1].children;
  assert.equal(cells.length, 1);
  assert.equal(cells[0].dataset.tipTitle, 'Code');
});

test('icon_url 为 null 时用首字母块，不发请求', () => {
  const { root } = bandWith([hour(7, [app(1, '哔哩哔哩', 300, { icon_url: null })])]);
  const cell = root.children[7].children[1].children[0];
  assert.equal(cell.children[0].className, 'hour-band__initial');
  assert.equal(cell.children[0].textContent, '哔');
});

test('整块缺口换成斜纹说明块，而不是 24 行零', () => {
  const { root } = bandWith([hour(10, [app(1, 'Code', 600)])], { gap: true });
  assert.equal(root.children.length, 1);
  assert.equal(root.children[0].className, 'hour-band__gap');
  assert.match(root.children[0].textContent, /不是 0/);
});

test('destroy 之后不留节点', () => {
  const { band, root } = bandWith([hour(10, [app(1, 'Code', 600)])]);
  band.destroy();
  assert.equal(root.children.length, 0);
});
