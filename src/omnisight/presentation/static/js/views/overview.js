// 总览（06 文档 §5）。合并后最重要的界面：必须一眼看出时长与键盘的关系，
// 否则用户会觉得只是两个工具挤在一个窗口里。
//
// 取数：首屏只有 `/overview` 一个请求（05 文档 §2 的复合端点）。输入强度分布来自
// `/insights/app-keyboard`，作为**第二个独立请求**异步补齐——它有自己的骨架屏，
// 不阻塞首屏的指标卡与时间线（07 文档 §5.2）。
import { h, mount, setText } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { panelPair } from '../charts/panel-pair.js';
import { stackBar } from '../components/stack-bar.js';
import { markGaps, stackByCategory } from '../domain/buckets.js';
import { formatCount, formatDuration, formatPercent } from '../domain/format.js';
import { gapSet, periodParams } from '../domain/period.js';
import { renderAppRows } from '../components/app-list.js';
import { capabilityNotice, emptyState, errorState, gapLegend, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { renderHighlights as renderHighlightList } from '../components/highlights.js';
import { segmented } from '../components/controls.js';
import { statCard } from '../components/stat-card.js';
import { card } from '../components/card.js';

export const title = '总览';

// 「双轴」被删掉了：两套刻度画在一张图里会编造相关性（14 文档 §2.1）。取而代之的
// 「强度」是把两个量放到一根轴上的合法做法——取派生量 KPM，一条线一套刻度。
const TIMELINE_MODES = [
  { id: 'both', name: '并排' },
  { id: 'seconds', name: '时长' },
  { id: 'presses', name: '按键' },
  { id: 'kpm', name: '强度' },
];

const GRAIN_NAMES = { hour: '小时', day: '天', month: '月', year: '年' };

export function create(root) {
  let mode = 'both';

  const screen = statCard({
    label: '屏幕时间',
    hint: '前台应用的累计时长，已扣除空闲',
    hero: true,
    series: 'time',
    metric: 'seconds',
    format: formatDuration,
  });
  const keyboard = statCard({
    label: '按键',
    hint: '按键次数。不记录按了什么内容',
    series: 'keys',
    metric: 'presses',
    format: (value) => `${formatCount(value)} 次`,
  });

  const timelineHost = h('div', { class: 'chart chart--tall' });
  const timelineNote = h('div', { class: 'card__hint' });
  const gapNote = h('div');
  const legendHost = h('div', { class: 'chart__legend' });
  const modeTabs = segmented(TIMELINE_MODES, mode, (id) => {
    mode = id;
    modeTabs.setActive(id);
    render();
  }, { small: true, label: '活动带指标' });

  const categoryHost = h('div', { class: 'category-list' });
  const categoryBarHost = h('div');
  const intensityBarHost = h('div');
  const intensityLegend = h('div', { class: 'category-list' });
  const appsHost = h('div', { class: 'app-list' });
  const highlightsHost = h('div', { class: 'highlights' });

  const chart = panelPair(timelineHost, { height: 220, label: '活动带' });
  const categoryBar = stackBar(categoryBarHost, { label: '类别构成' });
  const intensityBar = stackBar(intensityBarHost, { label: '输入强度构成' });

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '总览', attrs: { tabindex: '-1', id: 'view-title' } }),
    card('活动带', h('div', null, timelineHost, legendHost, gapNote), [modeTabs.root], timelineNote),
    h('div', { class: 'overview__pair' }, screen.root, keyboard.root),
    card(
      '构成',
      h(
        'div',
        { class: 'overview__stacks' },
        h('div', null, h('div', { class: 'overview__stack-label', text: '时间去了哪些类别' }), categoryBarHost, categoryHost),
        h('div', null, h('div', { class: 'overview__stack-label', text: '其中多少是在真的输入' }), intensityBarHost, intensityLegend),
      ),
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
    // 两张卡共用一条对照序列（后端一次算好 seconds 与 presses），各取自己那一列：
    // 屏幕时间比时长、按键比次数，"这段时间算不算多"因此在两张卡上是同一把尺子。
    const context = overview.context || null;
    screen.update({
      text: time.total_formatted || formatDuration(time.total_seconds || 0),
      deltaValue: timeDelta,
      contextSeries: context,
      footnote: `${time.app_count || 0} 个应用，日均 ${formatDuration(time.daily_average_seconds || 0)}`,
    });
    keyboard.update({
      text: `${formatCount(keys.total_presses || 0)} 次`,
      deltaValue: keyDelta,
      contextSeries: context,
      footnote: `${keys.active_keys || 0} 个活跃键，峰值 ${formatCount(keys.kpm_peak || 0)} KPM`,
    });
    const grain = GRAIN_NAMES[overview.trend && overview.trend.granularity] || '时间';
    setText(timelineNote, `${overview.period ? overview.period.days : 0} 天，按${grain}聚合`);
  }

  function renderTimeline(overview, state) {
    const trend = overview.trend || {};
    const granularity = trend.granularity || 'hour';
    // 上下两个面板共享时间轴，缺口取两者的并集：任何一侧测不到，这个桶就不可信。
    const gaps = gapSet(state.coverage, ['foreground', 'keyboard']);
    const buckets = markGaps(stackByCategory(trend.buckets, overview.categories), granularity, gaps, overview.period);
    chart.update({
      buckets,
      mode,
      caption: '活动带',
      summary: `${(overview.period && overview.period.label) || ''}，共 ${buckets.length} 个时间桶`,
    });
    // 两个系列必须有图例，且常驻（14 文档 §4.3）。上面板按类别着色，因此时长那一侧
    // 的图例就是类别本身——一个蓝色"屏幕时间"色块会与柱子的实际颜色对不上。
    const categories = (overview.categories || []).filter((item) => (item.seconds || 0) > 0);
    const showTime = mode === 'both' || mode === 'seconds';
    mount(
      legendHost,
      showTime && categories.length
        ? categories.map((item) =>
            h('span', { class: 'chart__legend-item', dataset: { category: item.id } }, h('i'), h('span', { text: item.name })))
        : null,
      showTime && !categories.length
        ? h('span', { class: 'chart__legend-item', dataset: { series: 'time' } }, h('i'), h('span', { text: '屏幕时间' }))
        : null,
      mode === 'both' || mode === 'presses' || mode === 'kpm'
        ? h('span', { class: 'chart__legend-item', dataset: { series: 'keys' } }, h('i'), h('span', { text: mode === 'kpm' ? '输入强度 KPM' : '按键' }))
        : null,
    );
    mount(gapNote, gapLegend(gaps.size));
  }

  function renderCategories(overview) {
    const categories = overview.categories || [];
    // 槽位顺序 = 后端下发的顺序，不按大小排：相邻关系因此确定、可事先校验，
    // 且同一个类别在每个周期都在同一个位置（14 文档 §2.10）。
    categoryBar.update(
      categories.map((item) => ({
        id: item.id,
        name: item.name,
        value: item.seconds,
        percent: item.percent,
        formatted: item.seconds_formatted,
      })),
    );
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
    // 每条结论可点开看计算口径（M4 判据 4），渲染实现与洞察视图共用一份。
    renderHighlightList(highlightsHost, overview.highlights);
  }

  function renderIntensity(state) {
    const payload = state.data.overviewIntensity;
    if (!payload) {
      if (state.loading.overviewIntensity) mount(intensityLegend, skeletonRows(2));
      return;
    }
    const distribution = payload.distribution || {};
    const buckets = distribution.buckets || [];
    const total = Number(distribution.total_seconds) || 0;
    // 与类别构成条上下对齐、共用同一条 100% 宽度基准：同一张卡回答"时间去了哪些
    // 类别"和"其中多少是在真的输入"（14 文档 §4.3）。
    intensityBar.update(
      buckets.map((item) => ({
        id: item.id,
        name: item.name,
        value: item.seconds,
        percent: total ? ((item.seconds || 0) / total) * 100 : 0,
        formatted: item.seconds_formatted,
      })),
    );
    mount(
      intensityLegend,
      ...buckets.map((item) =>
        h(
          'div',
          { class: 'category-row', dataset: { profile: item.id } },
          h('span', { class: 'swatch', attrs: { 'aria-hidden': 'true' } }),
          h('span', { class: 'truncate', text: item.name }),
          h('span', {
            class: 'category-row__percent',
            text: formatPercent(total ? ((item.seconds || 0) / total) * 100 : 0),
          }),
          h('span', { class: 'category-row__value', text: item.seconds_formatted }),
        ),
      ),
      // 总量守恒：没有归因的按键必须显示出来，否则各应用之和与指标卡对不上而用户
      // 无从发现原因（04 文档 §2.2 的 app_id = 0）。
      payload.unattributed_presses
        ? h('div', {
            class: 'card__hint',
            text: `另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`,
          })
        : null,
    );
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
      categoryBar.destroy();
      intensityBar.destroy();
      screen.destroy();
      keyboard.destroy();
      root.replaceChildren();
    },
  };
}
