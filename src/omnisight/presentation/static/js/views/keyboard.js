// 键盘视图（06 文档 §7）。
//
// 与旧 KeyTrace 的三处关键差异：
//   1. 键盘 DOM 由 `/keyboard/layout` 下发的数据生成，前端零坐标（旧版是 860 行硬编码）。
//   2. 范围切换（全部应用 / 某个应用）就在顶部，它是同一张热力图的两种范围，不是两个
//      功能——旧版把它塞在页面最下方一个独立面板里，还需要另外连上 TimeLens。
//   3. 时间分布四个粒度**一次请求取回**（`view=hours,days,months,years`），旧版首屏
//      为此发 4 个请求。
import { h, mount } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { fetchInto } from '../core/loader.js';
import { barChart } from '../charts/bar-chart.js';
import { calendarHeatmap } from '../charts/calendar-heatmap.js';
import { markGaps } from '../domain/buckets.js';
import { formatCount, formatPercent } from '../domain/format.js';
import { METRICS, TIMELINE_VIEWS, formatMetric } from '../domain/metrics.js';
import { appPicker } from '../components/app-picker.js';
import { keyboardView } from '../components/keyboard-view.js';
import { segmented } from '../components/controls.js';
import { capabilityNotice, emptyState, errorState, gapLegend, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { card } from '../components/card.js';
import { caliberNotes, gapSet, periodParams } from '../domain/period.js';

export const title = '键盘';

const TOP_KEYS = 10;

export function create(root) {
  // 不传 onChange：picker 自己 setState('scopeAppId')，main.js 的订阅会重新取数。
  // 这里再调一次 reload() 就是每次切范围发两遍请求。
  const picker = appPicker();
  const metricTabs = segmented(METRICS, getState().metric, (id) => {
    setState('metric', id);
    metricTabs.setActive(id);
  }, { small: true, label: '指标' });

  const totalsHost = h('div', { class: 'keyboard-totals' });
  const boardHost = h('div');
  const boardNotice = h('div');
  const grainTabs = segmented(TIMELINE_VIEWS, getState().timelineView, (id) => {
    setState('timelineView', id);
    grainTabs.setActive(id);
  }, { small: true, label: '时间粒度' });
  const timelineHost = h('div', { class: 'chart chart--medium' });
  const timelineNote = h('div');
  const topKeysHost = h('div', { class: 'top-keys' });
  const fingersHost = h('div');
  const calendarHost = h('div');
  const calendarNote = h('div');

  const board = keyboardView(boardHost, {
    onSelectKey: (keyId) => {
      setState('selectedKeyId', keyId);
      loadKeyDetail(keyId);
    },
  });
  const timeline = barChart(timelineHost, { height: 150, label: '按键时间分布' });
  const calendar = calendarHeatmap(calendarHost, {
    weekStartsOn: getState().prefs.weekStartsOn,
    metric: 'press_count',
  });

  const keyDetailHost = h('div');

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '键盘', attrs: { tabindex: '-1', id: 'view-title' } }),
    card('键盘热力图', h('div', null, boardNotice, boardHost), [picker.root, metricTabs.root], totalsHost),
    keyDetailHost,
    card('时间分布', h('div', null, timelineHost, timelineNote), [grainTabs.root]),
    h(
      'div',
      { class: 'grid grid--2' },
      card(`高频键位 Top ${TOP_KEYS}`, topKeysHost),
      card('手指负荷', fingersHost),
    ),
    card('每日活跃度（近 365 天）', h('div', null, calendarHost, calendarNote)),
  );

  let renderedFamily = null;

  function render() {
    const state = getState();
    const heatmap = state.data.heatmap;
    const layout = state.data.layout;
    const error = state.errors.heatmap || state.errors.layout;

    // 键盘采集不可用：整块面板换成说明块。这里绝不画一张全 0 的键盘——那会让用户
    // 以为自己没打字，而真相是这台机器测不到（06 文档 §4.2 规则 1）。
    if (!capabilityOf(state.capabilities, 'keyboard')) {
      const notice = noticeFor(state.degraded, 'keyboard');
      mount(boardNotice, capabilityNotice({
        title: (notice && notice.title) || '当前环境无法采集键盘',
        detail: (notice && notice.detail) || '应用时长统计不受影响。',
        hint: (notice && notice.hint) || '',
      }));
      mount(boardHost);
      mount(totalsHost);
      return;
    }
    mount(boardNotice, caliberNotice(state.coverage));

    if (error) {
      mount(boardHost, errorState({ message: error.message, onRetry: reload }));
      return;
    }
    if (!layout || !heatmap) {
      if (state.loading.heatmap || state.loading.layout) mount(totalsHost, skeletonRows(1));
      return;
    }

    if (renderedFamily !== layout.family) {
      // 布局变了才重建 DOM；热力数据不必重取——keys 按 id 匹配，与布局无关。
      board.setLayout(layout);
      renderedFamily = layout.family;
    }
    board.update(heatmap, state.metric);
    renderTotals(heatmap);
    renderTopKeys(heatmap, state.metric);
    picker.update(pickerApps(state));
    renderTimeline(state);
    renderCalendar(state);
    renderErgonomics(state);
    renderKeyDetail(state);
  }

  function renderTotals(heatmap) {
    const totals = heatmap.totals || {};
    const scope = heatmap.scope || {};
    mount(
      totalsHost,
      total('按键次数', formatCount(totals.press_count || 0)),
      total('活跃键位', `${totals.active_keys || 0} 个`),
      total('平均时长', formatMetric('duration_avg_ms', totals.duration_avg_ms || 0)),
      total('最长按压', formatMetric('duration_max_ms', totals.duration_max_ms || 0)),
      scope.type === 'app'
        ? h('div', { class: 'card__hint', text: `范围：${scope.display_name || ''}` })
        : null,
    );
  }

  function renderTopKeys(heatmap, metric) {
    const keys = (heatmap.keys || [])
      .filter((key) => (Number(key[metric]) || 0) > 0)
      .sort((left, right) => (Number(right[metric]) || 0) - (Number(left[metric]) || 0))
      .slice(0, TOP_KEYS);
    if (!keys.length) {
      mount(topKeysHost, emptyState({ title: '这段时间没有按键记录', mark: '⌨' }));
      return;
    }
    const top = Number(keys[0][metric]) || 1;
    mount(
      topKeysHost,
      ...keys.map((key, index) =>
        h(
          'div',
          { class: 'top-key' },
          h('span', { class: 'rank', text: String(index + 1) }),
          h('span', { class: 'top-key__label', text: key.label }),
          bar((Number(key[metric]) || 0) / top),
          h('span', { class: 'top-key__count', text: formatMetric(metric, key[metric]) }),
          h('span', { class: 'top-key__percent', text: formatPercent(key.percent) }),
        ),
      ),
    );
  }

  function renderErgonomics(state) {
    const payload = state.data.ergonomics;
    if (!payload) {
      if (state.loading.ergonomics) mount(fingersHost, skeletonRows(3));
      return;
    }
    const hands = payload.hands || {};
    const left = Number(hands.left) || 0;
    const right = Number(hands.right) || 0;
    const both = left + right;
    const handBar = h('div', { class: 'hands__bar' }, h('i'), h('i'));
    handBar.style.setProperty('--left', both ? String(left / both) : '0.5');
    const fingers = payload.fingers || [];
    const top = Math.max(1, ...fingers.map((finger) => Number(finger.press_count) || 0));
    mount(
      fingersHost,
      h(
        'div',
        { class: 'hands' },
        h('span', { text: `左手 ${formatPercent(both ? (left / both) * 100 : 0)}` }),
        handBar,
        h('span', { text: `右手 ${formatPercent(both ? (right / both) * 100 : 0)}` }),
      ),
      h(
        'div',
        { class: 'fingers' },
        ...fingers.map((finger) =>
          h(
            'div',
            { class: 'finger-row' },
            h('span', { class: 'finger-row__name', text: finger.name }),
            bar((Number(finger.press_count) || 0) / top),
            h('span', { class: 'finger-row__percent', text: formatPercent(finger.percent) }),
          ),
        ),
      ),
      // 修饰键占比的口径必须写明：数的是修饰键**自身**被按下的次数，不是"按某个键时
      // 按住了修饰键"——后者需要和弦信息，而我们不记录按键顺序（08 文档 §2）。
      payload.modifier_ratio
        ? h('div', {
            class: 'card__hint',
            text: `修饰键占比 ${formatPercent(payload.modifier_ratio.percent)}，口径：修饰键自身被按下的次数`,
          })
        : null,
      // 左右修饰键无法区分时，手指负荷的左右分布会失真——如实说明。
      capabilityOf(state.capabilities, 'key_position_stable')
        ? null
        : h('div', { class: 'card__hint', text: '当前后端无法区分左右修饰键，左右手分布仅供参考' }),
    );
  }

  function renderTimeline(state) {
    const payload = state.data.timeline;
    if (!payload) {
      if (state.loading.timeline) mount(timelineNote, skeletonRows(1));
      return;
    }
    const grain = state.timelineView;
    const view = (payload.views || {})[grain];
    // available: false 是"该视图在当前设置下拿不到"，不是"值为 0"。原始事件被关掉时
    // 按小时的应用维度分布就属于这一类（services/keyboard.py 的 _hours_view）。
    if (!view || view.available === false) {
      timeline.update({ buckets: [], mode: 'presses' });
      mount(timelineNote, capabilityNotice({
        title: '该视图在当前设置下不可用',
        detail: warningText(payload) || '按小时的应用维度分布需要保留原始按键事件。',
        hint: '设置中开启"保存原始按键事件"后，此后的数据可用',
      }));
      return;
    }
    const gaps = gapSet(state.coverage, ['keyboard']);
    const buckets = markGaps(view.buckets || [], grainOf(grain), gaps, view.period);
    timeline.update({
      buckets: buckets.map((bucket) => ({ ...bucket, presses: bucket[state.metric] })),
      mode: 'presses',
      caption: '按键时间分布',
      summary: `按${grainName(grain)}的按键分布，共 ${buckets.length} 个桶`,
    });
    mount(timelineNote, gapLegend(gaps.size));
  }

  function renderCalendar(state) {
    const payload = state.data.timeline;
    const view = payload && payload.views && payload.views.days;
    if (!view || view.available === false) return;
    const gaps = gapSet(state.coverage, ['keyboard']);
    calendar.update(view.buckets || [], view.scale, gaps);
    mount(calendarNote, gapLegend(gaps.size));
  }

  function renderKeyDetail(state) {
    const keyId = state.selectedKeyId;
    const payload = state.data.keyDetail;
    if (!keyId) {
      mount(keyDetailHost);
      return;
    }
    if (!payload || payload.key.id !== keyId) {
      mount(keyDetailHost, card('键位详情', skeletonRows(2)));
      return;
    }
    const key = payload.key;
    const totals = payload.totals || {};
    const byApp = payload.by_app || [];
    const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
    mount(
      keyDetailHost,
      card(
        `键位详情：${key.label}`,
        h(
          'div',
          { class: 'stack' },
          h('dl', { class: 'kv-list' },
            h('dt', { text: '按下次数' }), h('dd', { text: formatCount(totals.press_count || 0) }),
            h('dt', { text: '平均时长' }), h('dd', { text: formatMetric('duration_avg_ms', totals.duration_avg_ms || 0) }),
            h('dt', { text: '手指' }), h('dd', { text: key.finger_name || '-' }),
            h('dt', { text: '所在行' }), h('dd', { text: key.row_name || '-' }),
            h('dt', { text: '在当前布局中' }), h('dd', { text: key.in_layout ? '是' : '否' })),
          byApp.length
            ? h('div', { class: 'key-app-split' },
                h('div', { class: 'text-sm muted', text: '主要来自这些应用' }),
                ...byApp.slice(0, 8).map((item) =>
                  h('div', { class: 'top-key' },
                    h('span', { class: 'rank' }),
                    h('span', { class: 'truncate', text: item.display_name }),
                    bar((Number(item.press_count) || 0) / top),
                    h('span', { class: 'top-key__count', text: formatCount(item.press_count) }),
                    h('span', { class: 'top-key__percent', text: formatPercent(item.percent) })),
                ))
            : h('div', { class: 'card__hint', text: '这个键没有按应用拆分的数据' }),
        ),
        [h('button', {
          class: 'button', type: 'button', text: '关闭',
          on: { click: () => setState('selectedKeyId', null) },
        })],
      ),
    );
  }

  function loadKeyDetail(keyId) {
    fetchInto('keyDetail', `/keyboard/keys/${keyId}`, periodParams(getState().period));
  }

  function reload() {
    const state = getState();
    for (const request of requestsFor(state)) {
      fetchInto(request.key, request.path, request.params);
    }
  }

  function requestsFor(state) {
    const period = periodParams(state.period);
    const scope = state.scopeAppId ? { app_id: state.scopeAppId } : {};
    const requests = [
      { key: 'layout', path: '/keyboard/layout', params: familyParam(state) },
      { key: 'heatmap', path: '/keyboard/heatmap', params: { ...period, metric: state.metric, ...scope } },
      {
        key: 'timeline',
        path: '/keyboard/timeline',
        // 四个粒度一次取回：KeyTrace 首屏为此发 4 个请求（05 文档 §4）。
        params: { ...period, view: 'hours,days,months,years', metric: state.metric, ...scope },
      },
      { key: 'ergonomics', path: '/keyboard/ergonomics', params: { ...period, ...scope } },
      { key: 'appsMeta', path: '/apps', params: { limit: 300 } },
    ];
    if (state.selectedKeyId) {
      requests.push({ key: 'keyDetail', path: `/keyboard/keys/${state.selectedKeyId}`, params: period });
    }
    return requests;
  }

  return {
    needs: requestsFor,
    render,
    destroy() {
      board.destroy();
      timeline.destroy();
      calendar.destroy();
      root.replaceChildren();
    },
  };
}

/** 布局族：auto 时不传 family，让后端按平台默认值决定（05 文档 §7）。 */
function familyParam(state) {
  const requested = state.prefs.keyboardLayout;
  return requested && requested !== 'auto' ? { family: requested } : {};
}

function pickerApps(state) {
  const meta = state.data.appsMeta;
  return (meta && meta.apps) || [];
}

function total(label, value) {
  return h(
    'div',
    null,
    h('div', { class: 'keyboard-total__label', text: label }),
    h('div', { class: 'keyboard-total__value numeric', text: value }),
  );
}

function bar(ratio) {
  const node = h('div', { class: 'bar' }, h('i'));
  node.style.setProperty('--fill', String(Math.max(0, Math.min(1, ratio || 0))));
  return node;
}

function grainOf(view) {
  return view === 'hours' ? 'hour' : view === 'days' ? 'day' : view === 'months' ? 'month' : 'year';
}

function grainName(view) {
  return { hours: '小时', days: '天', months: '月', years: '年' }[view] || '时间';
}

function warningText(payload) {
  const warnings = (payload && payload.warnings) || [];
  return warnings.length ? warnings[0].message : '';
}

/** 口径变化（左右修饰键合并）不是缺数据，用注记而不是斜纹表达。 */
function caliberNotice(coverage) {
  const notes = caliberNotes(coverage);
  if (!notes.length) return null;
  const note = notes[0];
  return h('div', {
    class: 'card__hint',
    text: `${note.from} 至 ${note.to} 的数据口径不同：${note.message}`,
  });
}
