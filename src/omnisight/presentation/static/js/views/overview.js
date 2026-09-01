// 总览（06 文档 §5）。合并后最重要的界面：必须一眼看出时长与键盘的关系，
// 否则用户会觉得只是两个工具挤在一个窗口里。
//
// 取数：首屏只有 `/overview` 一个请求（05 文档 §2 的复合端点）。输入强度分布来自
// `/insights/app-keyboard`，作为**第二个独立请求**异步补齐——它有自己的骨架屏，
// 不阻塞首屏的指标卡与时间线（07 文档 §5.2）。
import { h, mount, setText } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { barChart } from '../charts/bar-chart.js';
import { donut } from '../charts/donut.js';
import { markGaps } from '../domain/buckets.js';
import { formatCount, formatDuration, formatPercent } from '../domain/format.js';
import { gapSet, periodParams } from '../domain/period.js';
import { renderAppRows } from '../components/app-list.js';
import { capabilityNotice, emptyState, errorState, gapLegend, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { segmented } from '../components/controls.js';
import { meterRow, statCard } from '../components/stat-card.js';
import { card } from '../components/card.js';

export const title = '总览';

const TIMELINE_MODES = [
  { id: 'seconds', name: '时长' },
  { id: 'presses', name: '按键' },
  { id: 'both', name: '双轴' },
];

const GRAIN_NAMES = { hour: '小时', day: '天', month: '月', year: '年' };

function ratioOf(current, deltaValue) {
  const now = Number(current) || 0;
  const previous = now - (Number(deltaValue) || 0);
  if (previous <= 0) return now > 0 ? 1 : 0;
  return Math.min(1, now / Math.max(now, previous));
}

export function create(root) {
  let mode = 'both';

  const screen = statCard({ label: '屏幕时间', hint: '前台应用的累计时长，已扣除空闲' });
  const keyboard = statCard({ label: '键盘活动', hint: '按键次数。不记录按了什么内容' });

  const timelineHost = h('div', { class: 'chart chart--tall' });
  const timelineNote = h('div', { class: 'card__hint' });
  const gapNote = h('div');
  const modeTabs = segmented(TIMELINE_MODES, mode, (id) => {
    mode = id;
    modeTabs.setActive(id);
    render();
  }, { small: true, label: '时间线指标' });

  const categoryHost = h('div', { class: 'category-list' });
  const donutHost = h('div', { class: 'chart chart--medium' });
  const intensityHost = h('div', { class: 'intensity' });
  const appsHost = h('div', { class: 'app-list' });
  const highlightsHost = h('div', { class: 'highlights' });

  const chart = barChart(timelineHost, { height: 200, label: '活动时间线' });
  const pie = donut(donutHost, { height: 160, label: '类别占比' });
  const meters = new Map();

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '总览', attrs: { tabindex: '-1', id: 'view-title' } }),
    h('div', { class: 'overview__pair' }, screen.root, keyboard.root),
    card('活动时间线', h('div', null, timelineHost, gapNote), [modeTabs.root], timelineNote),
    h(
      'div',
      { class: 'grid grid--2' },
      card('应用分布', h('div', null, donutHost, categoryHost)),
      card('输入强度分布', intensityHost, [], h('div', {
        class: 'card__hint',
        text: '按 KPM 划分：主动输入 / 交互 / 被动消费 / 开着未用',
      })),
    ),
    card('最常使用', appsHost, [
      h('button', {
        class: 'card__link',
        type: 'button',
        text: '查看全部',
        dataset: { action: 'route:go', route: 'apps' },
      }),
    ]),
    card('结论', highlightsHost),
  );

  function render() {
    const state = getState();
    const overview = state.data.overview;
    const error = state.errors.overview;

    if (error) {
      mount(appsHost, errorState({ message: error.message, onRetry: reload }));
      return;
    }
    if (!overview) {
      if (state.loading.overview) {
        screen.loading();
        keyboard.loading();
        mount(appsHost, skeletonRows(4));
      }
      return;
    }

    renderMetrics(overview);
    renderTimeline(overview, state);
    renderCategories(overview);
    renderTopApps(overview, state);
    renderHighlights(overview);
    renderIntensity(state);
  }

  function renderMetrics(overview) {
    const time = overview.screen_time || {};
    const keys = overview.keyboard || {};
    const timeDelta = time.delta_vs_previous;
    const keyDelta = keys.delta_vs_previous;
    screen.update({
      text: time.total_formatted || formatDuration(time.total_seconds || 0),
      deltaValue: timeDelta,
      ratio: ratioOf(time.total_seconds, timeDelta && timeDelta.seconds),
      footnote: `${time.app_count || 0} 个应用，日均 ${formatDuration(time.daily_average_seconds || 0)}`,
    });
    keyboard.update({
      text: `${formatCount(keys.total_presses || 0)} 次`,
      deltaValue: keyDelta,
      ratio: ratioOf(keys.total_presses, keyDelta && keyDelta.presses),
      footnote: `${keys.active_keys || 0} 个活跃键，峰值 ${formatCount(keys.kpm_peak || 0)} KPM`,
    });
    const grain = GRAIN_NAMES[overview.trend && overview.trend.granularity] || '时间';
    setText(timelineNote, `${overview.period ? overview.period.days : 0} 天，按${grain}聚合`);
  }

  function renderTimeline(overview, state) {
    const trend = overview.trend || {};
    const granularity = trend.granularity || 'hour';
    // 时长与按键两条曲线画在一起，缺口取两者的并集：任何一侧测不到，这个桶就不可信。
    const gaps = gapSet(state.coverage, ['foreground', 'keyboard']);
    const buckets = markGaps(trend.buckets || [], granularity, gaps, overview.period);
    chart.update({
      buckets,
      mode,
      caption: '活动时间线',
      summary: `${(overview.period && overview.period.label) || ''}，共 ${buckets.length} 个时间桶`,
    });
    mount(gapNote, gapLegend(gaps.size));
  }

  function renderCategories(overview) {
    const categories = overview.categories || [];
    pie.update({
      slices: categories.map((item) => ({
        id: item.id,
        name: item.name,
        value: item.seconds,
        percent: item.percent,
      })),
    });
    const rows = categories.map((item) =>
      h(
        'div',
        { class: 'category-row', dataset: { category: item.id } },
        h('span', { class: 'swatch', attrs: { 'aria-hidden': 'true' } }),
        h('span', { class: 'truncate', text: item.name }),
        h('span', { class: 'category-row__percent', text: formatPercent(item.percent) }),
        h('span', { class: 'category-row__value', text: item.seconds_formatted }),
      ),
    );
    const empty = emptyState({
      title: '这段时间没有应用记录',
      detail: '换一个日期，或确认采集正在运行',
    });
    mount(categoryHost, ...rows, categories.length ? null : empty);
  }

  function renderTopApps(overview, state) {
    const apps = overview.top_apps || [];
    // 归因不可用时，显示"0 个应用"是错的说法：面板正文换成能力说明块，
    // 且**不给重试按钮**——重试不会改变结果（06 文档 §4.2 第二级、§10.1）。
    if (!capabilityOf(state.capabilities, 'foreground')) {
      const notice = noticeFor(state.degraded, 'foreground');
      mount(appsHost, capabilityNotice({
        title: (notice && notice.title) || '当前环境不支持识别前台应用',
        detail: (notice && notice.detail) || '键盘统计不受影响，但无法按应用拆分时长。',
        hint: (notice && notice.hint) || '',
      }));
      return;
    }
    if (!apps.length) {
      mount(appsHost, emptyState({
        title: '这段时间没有使用记录',
        detail: '把范围切到全部即可查看历史数据',
      }));
      return;
    }
    const maxSeconds = Math.max(...apps.map((app) => app.seconds || 0));
    const maxKpm = Math.max(...apps.map((app) => app.kpm || 0));
    renderAppRows(appsHost, apps.slice(0, 6), { maxSeconds, maxKpm });
  }

  function renderHighlights(overview) {
    const highlights = overview.highlights || [];
    const rows = highlights.map((item) =>
      h(
        'div',
        { class: 'highlight' },
        h('span', { class: 'highlight__mark', attrs: { 'aria-hidden': 'true' }, text: '◈' }),
        h('span', { text: item.text }),
      ),
    );
    const fallback = h('div', { class: 'dim text-sm', text: '数据还不够多，暂时得不出结论' });
    mount(highlightsHost, ...rows, highlights.length ? null : fallback);
  }

  function renderIntensity(state) {
    const payload = state.data.overviewIntensity;
    if (!payload) {
      if (state.loading.overviewIntensity) mount(intensityHost, skeletonRows(3));
      return;
    }
    const distribution = payload.distribution || {};
    const buckets = distribution.buckets || [];
    const total = Number(distribution.total_seconds) || 0;
    mount(intensityHost);
    for (const bucket of buckets) {
      let meter = meters.get(bucket.id);
      if (!meter) {
        meter = meterRow({ name: bucket.name, profile: bucket.id });
        meters.set(bucket.id, meter);
      }
      meter.update(total ? (bucket.seconds || 0) / total : 0, bucket.seconds_formatted);
      intensityHost.append(meter.root);
    }
    // 总量守恒：没有归因的按键必须显示出来，否则各应用之和与指标卡对不上而用户
    // 无从发现原因（04 文档 §2.2 的 app_id = 0）。
    if (payload.unattributed_presses) {
      intensityHost.append(h('div', {
        class: 'card__hint',
        text: `另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`,
      }));
    }
  }

  function reload() {
    setState('period', { ...getState().period });
  }

  return {
    needs(state) {
      const period = periodParams(state.period);
      return [
        { key: 'overview', path: '/overview', params: period },
        { key: 'overviewIntensity', path: '/insights/app-keyboard', params: { ...period, limit: 8 } },
      ];
    },
    render,
    destroy() {
      chart.destroy();
      pie.destroy();
      root.replaceChildren();
    },
  };
}
