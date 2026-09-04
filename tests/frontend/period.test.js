// 周期翻页与缺口映射。这两处的 bug 都是**静默**的：
//   翻页算错 -> 用户看的是相邻的另一段时间，数字仍然自洽；
//   缺口漏标 -> "测不到"被画成 0，用户得出错误结论且无从察觉（06 文档 §4.2 规则 1）。
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  addDays, addMonths, addYears, bucketCoversGap, caliberNotes, canGoForward,
  fromISO, gapSet, isPageable, periodParams, shift, toISO,
} from '../../src/omnisight/presentation/static/js/domain/period.js';
import { markGaps, stackByCategory } from '../../src/omnisight/presentation/static/js/domain/buckets.js';

test('日期加减不跨时区漂移', () => {
  assert.equal(addDays('2026-09-02', 1), '2026-09-03');
  assert.equal(addDays('2026-09-01', -1), '2026-08-31');
  assert.equal(addDays('2026-02-28', 1), '2026-03-01');
  assert.equal(addDays('2024-02-28', 1), '2024-02-29');
});

test('月末加一个月钳到月末，不滑到下下个月', () => {
  assert.equal(addMonths('2026-01-31', 1), '2026-02-28');
  assert.equal(addMonths('2026-03-31', -1), '2026-02-28');
  assert.equal(addMonths('2026-12-15', 1), '2027-01-15');
  assert.equal(addYears('2024-02-29', 1), '2025-02-28');
});

test('shift 按范围取步长；total 与 custom 没有上一个', () => {
  assert.equal(shift('day', '2026-09-02', -1), '2026-09-01');
  assert.equal(shift('week', '2026-09-02', -1), '2026-08-26');
  assert.equal(shift('month', '2026-09-02', 1), '2026-10-02');
  assert.equal(shift('year', '2026-09-02', -1), '2025-09-02');
  assert.equal(shift('total', '2026-09-02', -1), '2026-09-02');
  assert.equal(shift('custom', '2026-09-02', 1), '2026-09-02');
  assert.equal(isPageable('total'), false);
  assert.equal(isPageable('day'), true);
});

test('未来方向的箭头要先置灰，而不是点了没反应', () => {
  assert.equal(canGoForward('day', '2026-09-02', '2026-09-02'), false);
  assert.equal(canGoForward('day', '2026-09-01', '2026-09-02'), true);
  assert.equal(canGoForward('total', '2026-09-01', '2026-09-02'), false);
});

test('periodParams：custom 用 start/end，其余用 date', () => {
  assert.deepEqual(periodParams({ range: 'day', date: '2026-09-02' }), { range: 'day', date: '2026-09-02' });
  assert.deepEqual(
    periodParams({ range: 'custom', start: '2026-01-01', end: '2026-01-31' }),
    { range: 'custom', start: '2026-01-01', end: '2026-01-31' },
  );
});

test('gapSet 按 missing 过滤，并展开 from/to 区间', () => {
  const coverage = {
    gaps: [
      { from: '2026-08-28', to: '2026-08-30', missing: 'foreground', reason: 'wayland' },
      { from: '2026-08-20', to: '2026-08-20', missing: 'keyboard', reason: 'permission' },
    ],
  };
  const foreground = gapSet(coverage, ['foreground']);
  assert.deepEqual([...foreground].sort(), ['2026-08-28', '2026-08-29', '2026-08-30']);
  assert.equal(gapSet(coverage, ['keyboard']).has('2026-08-20'), true);
  assert.equal(gapSet(coverage, ['keyboard']).has('2026-08-28'), false);
  assert.equal(gapSet(coverage, ['foreground', 'keyboard']).size, 4);
});

test('key_position 是口径变化，不是缺数据：绝不画成斜纹', () => {
  const coverage = {
    gaps: [{ from: '2026-08-10', to: '2026-08-11', missing: 'key_position', reason: 'pynput', message: '左右修饰键合并统计' }],
  };
  assert.equal(gapSet(coverage, ['keyboard']).size, 0);
  assert.equal(gapSet(coverage, ['foreground']).size, 0);
  const notes = caliberNotes(coverage);
  assert.equal(notes.length, 1);
  assert.match(notes[0].message, /修饰键/);
});

test('bucketCoversGap 把日缺口映射到月/年桶上', () => {
  const gaps = new Set(['2026-08-29']);
  assert.equal(bucketCoversGap('2026-08-29', gaps), true);
  assert.equal(bucketCoversGap('2026-08-28', gaps), false);
  assert.equal(bucketCoversGap('2026-08', gaps), true);
  assert.equal(bucketCoversGap('2026', gaps), true);
  assert.equal(bucketCoversGap('2025', gaps), false);
});

test('markGaps：单日视图里整天缺失 -> 24 个小时桶全标记', () => {
  const buckets = Array.from({ length: 24 }, (unused, hour) => ({ bucket: String(hour).padStart(2, '0'), seconds: 0 }));
  const gaps = new Set(['2026-08-29']);
  const marked = markGaps(buckets, 'hour', gaps, { start: '2026-08-29' });
  assert.equal(marked.every((bucket) => bucket.gap === true), true);
  const other = markGaps(buckets, 'hour', gaps, { start: '2026-08-30' });
  assert.equal(other.some((bucket) => bucket.gap), false);
});

test('markGaps 不改原数组（派生数据不入 store）', () => {
  const buckets = [{ bucket: '2026-08-29', seconds: 0 }];
  const marked = markGaps(buckets, 'day', new Set(['2026-08-29']), {});
  assert.equal(marked[0].gap, true);
  assert.equal(buckets[0].gap, undefined);
});

test('ISO 日期解析用本地时间，东八区不差一天', () => {
  const date = fromISO('2026-09-02');
  assert.equal(date.getFullYear(), 2026);
  assert.equal(date.getMonth(), 8);
  assert.equal(date.getDate(), 2);
  assert.equal(toISO(date), '2026-09-02');
  assert.equal(fromISO('nonsense'), null);
});

// ── stackByCategory：活动带上面板的类别堆叠（14 文档 §4.3） ──────────────
test('stackByCategory：各段之和等于桶高，且键序即后端序', () => {
  const buckets = [{ bucket: '10', label: '10:00', seconds: 900, presses: 12, categories: { development: 600, system: 300 } }];
  const [bucket] = stackByCategory(buckets, [
    { id: 'development', name: '开发' },
    { id: 'system', name: '系统' },
  ]);
  assert.deepEqual(bucket.parts.map((part) => part.category), ['development', 'system']);
  assert.deepEqual(bucket.parts.map((part) => part.name), ['开发', '系统']);
  assert.equal(bucket.parts.reduce((sum, part) => sum + part.seconds, 0), bucket.seconds);
});

test('stackByCategory：0 值的类别不占一段，全零桶退化成单色柱', () => {
  const [bucket] = stackByCategory(
    [{ bucket: '03', label: '03:00', seconds: 60, presses: 0, categories: { development: 60, system: 0 } }],
    [],
  );
  assert.deepEqual(bucket.parts.map((part) => part.category), ['development']);
  const [empty] = stackByCategory([{ bucket: '04', label: '04:00', seconds: 0, presses: 0, categories: {} }], []);
  assert.equal(empty.parts, undefined);
});

test('stackByCategory：缺 categories 的响应不报错，也不产生空段', () => {
  const [bucket] = stackByCategory([{ bucket: '05', label: '05:00', seconds: 30, presses: 0 }], []);
  assert.equal(bucket.parts, undefined);
  assert.deepEqual(stackByCategory(undefined, undefined), []);
});

test('stackByCategory：没有目录时用类别 id 兜底当名字', () => {
  const [bucket] = stackByCategory(
    [{ bucket: '06', label: '06:00', seconds: 10, presses: 0, categories: { development: 10 } }],
    undefined,
  );
  assert.equal(bucket.parts[0].name, 'development');
});
