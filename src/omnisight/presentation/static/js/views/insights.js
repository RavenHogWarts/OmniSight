// 洞察视图（06 文档 §8 + 12 文档 M4、14 文档 §2.9/§2.11/§4.5）。
// **合并才可能实现的分析**——这是"为什么要升级"的答案。
//
// 面板与数据来源：
//   输入强度排行  /insights/app-keyboard        —— 这一屏的头条；应用名可下钻到该应用的键盘热图
//   键位 x 应用   /keyboard/keys/{id}          —— 键位选择器按当前周期高频键动态生成（M3-6）
//   节奏对比      /insights/rhythm 的 hourly    —— 打字最密集时段 vs 屏幕最长时段（M4）
//   每小时去向    /usage/timeline               —— stacked-bar（分类堆叠，M3 遗留图表的消费者）
//   专注与作息    /insights/rhythm
//
// **"结论"与"时间去向"归总览**：两个视图各画一份同源数据，用户不知道该看哪一个
// （14 文档 §2.9）。总览回答"这段时间发生了什么"，洞察只做交叉分析。
import { h, mount } from '../core/dom.js';
import { getState, setState } from '../core/store.js';
import { fetchInto } from '../core/loader.js';
import { formatCount, formatClock, formatDurationShort, formatPercent } from '../domain/format.js';
import { capabilityNotice, emptyState, errorState, skeletonRows } from '../components/states.js';
import { capabilityOf, noticeFor } from '../components/degraded.js';
import { card } from '../components/card.js';
import { hourBand } from '../components/hour-band.js';
import { stackedBar } from '../charts/stacked-bar.js';
import { panelPair } from '../charts/panel-pair.js';
import { gapSet, periodParams } from '../domain/period.js';

export const title = '洞察';

/** 键位选择器最多列几个高频键。太多就失去了"挑一个看看"的意义。 */
const KEY_CHOICES_LIMIT = 12;

function bar(ratio, profile) {
  const node = h('div', { class: 'bar', dataset: profile ? { profile } : {} }, h('i'));
  node.style.setProperty('--fill', String(Math.max(0, Math.min(1, ratio || 0))));
  return node;
}

export function create(root) {
  const rankHost = h('div', { class: 'data-table__scroll' });
  const rankNote = h('div', { class: 'card__hint' });
  const attributionNote = h('div');
  const hourlyHost = h('div', { class: 'chart chart--medium' });
  const hourlyNote = h('div');
  const bandHost = h('div');
  const rhythmChartHost = h('div', { class: 'chart chart--medium' });
  const rhythmKvHost = h('div', { class: 'stack' });
  const focusHost = h('div', { class: 'stack' });
  const rhythmHost = h('div', { class: 'stack' });
  const keySplitHost = h('div', { class: 'key-app-split' });
  const keySelect = h(
    'select',
    { class: 'control', attrs: { 'aria-label': '选择键位' } },
  );

  keySelect.addEventListener('change', () => {
    setState('selectedKeyId', keySelect.value);
    fetchInto('insightKey', `/keyboard/keys/${keySelect.value}`, periodParams(getState().period));
  });

  const hourlyChart = stackedBar(hourlyHost, { height: 170, label: '每小时时间去向' });
  // 堆叠柱答"哪一类"，图标带答"是哪一个"——同一张卡两层，不再是两个面板
  // （16 文档 §A1；前身把后者藏在另一张卡的背面）。
  const band = hourBand(bandHost);
  // 24 小时的 KPM 是一维时间序列，默认形式是柱不是格子——格子热图适合"网格上比大小"
  // （日历的 7×53），不适合一维序列（14 文档 §2.11）。
  const rhythmChart = panelPair(rhythmChartHost, { height: 150, label: '每小时输入强度' });

  mount(
    root,
    h('h1', { class: 'view__title sr-only', text: '洞察', attrs: { tabindex: '-1', id: 'view-title' } }),
    card('输入强度排行', h('div', null, attributionNote, rankHost), [], rankNote),
    card('键位与应用', keySplitHost),
    card('节奏对比', h('div', null, rhythmChartHost, rhythmKvHost)),
    card(
      '每小时时间去向',
      h(
        'div',
        null,
        hourlyHost,
        hourlyNote,
        h('div', { class: 'text-sm muted', text: '这些小时里用的是哪些应用' }),
        bandHost,
      ),
    ),
    h(
      'div',
      { class: 'grid grid--2' },
      card('专注度', focusHost),
      card('作息', rhythmHost),
    ),
  );

  function render() {
    const state = getState();
    const keyboard = state.data.insightKeyboard;
    const rhythm = state.data.insightRhythm;
    const error = state.errors.insightKeyboard || state.errors.insightRhythm;

    // 洞察整体依赖应用归因：没有归因就只剩"某个键被按了多少次"，那不是洞察。
    if (!capabilityOf(state.capabilities, 'foreground')) {
      const notice = noticeFor(state.degraded, 'foreground');
      mount(rankHost, capabilityNotice({
        title: (notice && notice.title) || '当前环境不支持识别前台应用',
        detail: (notice && notice.detail) || '交叉分析需要把按键归到应用上，键盘总量统计不受影响。',
        hint: (notice && notice.hint) || '',
      }));
      mount(hourlyHost);
      mount(rhythmChartHost);
      mount(focusHost);
      mount(rhythmHost);
      return;
    }
    if (error) {
      mount(rankHost, errorState({ message: error.message, onRetry: reload }));
      return;
    }
    renderAttributionNotice(state);
    if (!keyboard) {
      if (state.loading.insightKeyboard) mount(rankHost, skeletonRows(5));
      return;
    }

    renderRanking(keyboard);
    renderHourly(state);
    renderRhythmContrast(rhythm, state);
    renderFocus(rhythm, state);
    renderRhythm(rhythm, state);
    renderKeySplit(state);
  }

  /**
   * 无应用归因的时段必须明说，不能让用户把"测不到"当成"没按键"（M4 判据 3）。
   * 两种来源：coverage.gaps 里 missing=foreground 的段（能力缺失/迁移数据），
   * 以及响应里单列的 unattributed_presses（空闲、锁屏、被排除应用期间的按键）。
   */
  function renderAttributionNotice(state) {
    const gaps = (state.coverage && state.coverage.gaps) || [];
    const unattributed = gaps.filter((gap) => gap && gap.missing === 'foreground');
    if (!unattributed.length) {
      mount(attributionNote);
      return;
    }
    mount(
      attributionNote,
      ...unattributed.map((gap) =>
        h('div', {
          class: 'card__hint',
          text: `${gap.from === gap.to ? gap.from : `${gap.from} 至 ${gap.to}`} 无应用归因：`
            + `该时段的按键不计入任何应用（${gap.message || '该环境不支持应用归因'}），不是零`,
        }),
      ),
    );
  }

  function renderRanking(payload) {
    const apps = payload.apps || [];
    if (!apps.length) {
      // 空列表有两种含义：真的没有使用，或按键都归不到应用上。后者要明说（判据 3）。
      const unattributed = Number(payload.unattributed_presses) || 0;
      mount(rankHost, emptyState({
        title: unattributed
          ? '该时段的按键没有应用归因'
          : '这段时间没有可分析的应用',
        detail: unattributed
          ? `${formatCount(unattributed)} 次按键发生在无法识别前台应用的时段，未计入任何应用`
          : '',
        mark: '·',
      }));
      mount(rankNote, h('span', { text: '' }));
      return;
    }
    const maxKpm = Math.max(1, ...apps.map((app) => Number(app.kpm) || 0));
    // 真实 table 而不是 div 堆叠：屏幕阅读器需要行列关系（06 文档 §13）。
    mount(
      rankHost,
      h(
        'table',
        { class: 'data-table' },
        h('caption', { class: 'sr-only', text: '各应用的输入强度' }),
        h(
          'thead',
          null,
          h(
            'tr',
            null,
            h('th', { text: '应用' }),
            h('th', { class: 'numeric', text: '前台时长' }),
            h('th', { class: 'numeric', text: '按键' }),
            h('th', { class: 'numeric', text: 'KPM' }),
            h('th', { class: 'numeric', text: '修饰键' }),
            h('th', { text: '画像' }),
          ),
        ),
        h(
          'tbody',
          null,
          ...apps.map((app) =>
            h(
              'tr',
              null,
              h(
                'td',
                { class: 'wide' },
                // 下钻：同一张键盘热力图换一个范围（06 文档 §7 的"范围切换"）。
                // 应用视图的详情里已有同款入口，这里让"输入强度排行"也能直达。
                h('button', {
                  class: 'link rank__app',
                  type: 'button',
                  text: app.display_name,
                  attrs: { title: `在键盘中查看 ${app.display_name}` },
                  on: {
                    click: () => {
                      setState('scopeAppId', app.app_id);
                      setState('route', 'keyboard');
                    },
                  },
                }),
                h('div', { class: 'rank__keys text-xs dim' }, topKeysLine(app)),
              ),
              h('td', { class: 'numeric', text: app.seconds_formatted }),
              h('td', { class: 'numeric', text: formatCount(app.presses) }),
              h('td', { class: 'numeric', text: (Number(app.kpm) || 0).toFixed(1) }),
              h('td', { class: 'numeric', text: formatPercent(app.modifier_percent) }),
              h(
                'td',
                null,
                h(
                  'span',
                  { class: 'profile-tag', dataset: { profile: app.profile } },
                  h('span', { class: 'profile-tag__bar' }, bar((Number(app.kpm) || 0) / maxKpm, app.profile)),
                  h('span', { text: app.profile_name }),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    const parts = [payload.kpm_basis ? `KPM 口径：${payload.kpm_basis}` : ''];
    if (payload.unattributed_presses) {
      parts.push(`另有 ${formatCount(payload.unattributed_presses)} 次按键没有应用归因`);
    }
    mount(rankNote, h('span', { text: parts.filter(Boolean).join('。') }));
  }

  /** 常用键一行小字：Space 980 · E 820 · 左Ctrl 610（M4 应用 × 键盘交付物）。 */
  function topKeysLine(app) {
    const keys = app.top_keys || [];
    if (!keys.length) return h('span', { text: '没有按键记录' });
    return h(
      'span',
      null,
      ...keys.slice(0, 3).flatMap((key, index) => [
        index ? h('span', { text: ' · ' }) : null,
        h('b', { text: key.label }),
        h('span', { text: ` ${formatCount(key.press_count)}` }),
      ]),
    );
  }

  /** 每小时时间去向：按应用类别堆叠的 24 小时柱（stacked-bar 的第一个消费者，M3-5）。 */
  function renderHourly(state) {
    const payload = state.data.insightTimeline;
    if (!payload) {
      if (state.loading.insightTimeline) mount(hourlyHost, skeletonRows(3));
      return;
    }
    const hours = payload.hours || [];
    const gaps = gapSet(state.coverage, ['foreground']);
    // 图标带的缺口只在"看的就是这一天、而这一天测不到"时才成立：多天聚合里某天缺失
    // 不该让 24 行全画斜纹，那种情况由下面那行注记说明。
    const period = payload.period || {};
    band.update({ hours, gap: (period.days || 0) <= 1 && gaps.has(period.start) });
    const buckets = hours.map((hour) => ({
      label: `${hour.hour}:00`,
      total: hour.total_seconds,
      presses: hour.presses,
      parts: Object.entries(hour.categories || {}).map(([category, seconds]) => ({
        category,
        seconds,
      })),
    }));
    hourlyChart.update({
      buckets,
      caption: '每小时时间去向',
      summary: '按应用类别分层的每小时前台时长，共 24 个小时',
    });
    mount(hourlyNote, gaps.size ? h('div', {
      class: 'card__hint',
      text: `${gaps.size} 天无应用归因，这些天的时长未计入各小时`,
    }) : null);
  }

  /**
   * 节奏对比（M4）：一天中打字最密集的时段 vs 屏幕时间最长的时段。
   * 上面一条 24 小时的 KPM 柱给"密度长什么样"，下面两行结论给出两个峰值的答案。
   */
  function renderRhythmContrast(rhythm, state) {
    if (!rhythm) {
      if (state.loading.insightRhythm) mount(rhythmKvHost, skeletonRows(2));
      return;
    }
    const hourly = rhythm.hourly || [];
    // panelPair 的 kpm 模式自己按 presses/seconds 算，所以这里如实给两个原始量。
    rhythmChart.update({
      buckets: hourly.map((item) => ({
        bucket: String(item.hour).padStart(2, '0'),
        label: `${item.hour}:00`,
        seconds: item.seconds,
        presses: item.presses,
      })),
      mode: 'kpm',
      caption: '每小时输入强度',
      summary: '一天 24 小时的输入强度（KPM）',
    });
    const peaks = rhythm.hour_peaks || {};
    const typing = peaks.typing;
    const screen = peaks.screen;
    mount(
      rhythmKvHost,
      h(
        'dl',
        { class: 'kv-list' },
        h('dt', { text: '打字最密集' }),
        h('dd', { text: typing ? `${typing.hour}:00（${(Number(typing.kpm) || 0).toFixed(1)} KPM）` : '—' }),
        h('dt', { text: '屏幕时间最长' }),
        h('dd', { text: screen ? `${screen.hour}:00（${formatDurationShort(screen.seconds)}）` : '—' }),
        typing && screen
          ? h('dt', { text: '是否同一时段' })
          : null,
        typing && screen
          ? h('dd', { text: peaks.same_hour ? '是——这段时间真正用在了输入上' : '否——屏幕最长的那小时更多在阅读或观看' })
          : null,
      ),
      typing || screen
        ? h('div', { class: 'card__hint', text: `口径：${peaks.typing_basis || rhythm.hourly_basis || ''}` })
        : null,
    );
  }

  function renderFocus(rhythm, state) {
    if (!rhythm) {
      if (state.loading.insightRhythm) mount(focusHost, skeletonRows(2));
      return;
    }
    const blocks = rhythm.focus_blocks || [];
    mount(
      focusHost,
      h(
        'dl',
        { class: 'kv-list' },
        h('dt', { text: '应用切换' }), h('dd', { text: `${formatCount(rhythm.switch_count)} 次` }),
        h('dt', { text: '每小时切换' }), h('dd', { text: (Number(rhythm.switches_per_hour) || 0).toFixed(1) }),
        h('dt', { text: '最长专注' }), h('dd', { text: `${(Number(rhythm.longest_focus_minutes) || 0).toFixed(0)} 分钟` }),
      ),
      // 切换次数的口径要写明：心跳切段不是切换，只有 end_reason = switch 才算
      // （否则这个数字会大两个数量级，见 03 文档的访问与会话段之分）。
      rhythm.switches_basis
        ? h('div', { class: 'card__hint', text: `口径：${rhythm.switches_basis}` })
        : null,
      blocks.length
        ? h(
            'div',
            { class: 'focus-blocks' },
            h('div', { class: 'text-sm muted', text: '最长的几段专注' }),
            ...blocks.slice(0, 6).map((block) =>
              h(
                'div',
                { class: 'focus-block' },
                h('span', { text: `${formatClock(block.start)}-${formatClock(block.end)}` }),
                h('span', { class: 'truncate', text: block.display_name }),
                h('span', { class: 'numeric', text: `${(Number(block.minutes) || 0).toFixed(0)} 分钟` }),
              ),
            ),
          )
        : h('div', { class: 'card__hint', text: '这段时间没有足够长的连续使用' }),
    );
  }

  function renderRhythm(rhythm, state) {
    if (!rhythm) {
      if (state.loading.insightRhythm) mount(rhythmHost, skeletonRows(2));
      return;
    }
    const active = rhythm.active_hours || {};
    const peak = rhythm.peak_kpm || {};
    mount(
      rhythmHost,
      h(
        'dl',
        { class: 'kv-list' },
        h('dt', { text: '首次活动' }), h('dd', { text: active.first || '-' }),
        h('dt', { text: '末次活动' }), h('dd', { text: active.last || '-' }),
        h('dt', { text: '活跃跨度' }), h('dd', { text: `${(Number(active.span_hours) || 0).toFixed(1)} 小时` }),
        h('dt', { text: '峰值 KPM' }), h('dd', { text: formatCount(peak.value || 0) }),
        h('dt', { text: '峰值时刻' }), h('dd', { text: peak.at ? formatClock(peak.at) : '-' }),
      ),
    );
  }

  /** 键位选择器：按当前周期的高频键动态生成（M3-6），不再硬编码 6 个键。 */
  function renderKeyChoices(state) {
    const heatmap = state.data.insightHeatmap;
    const current = state.selectedKeyId || '';
    if (!heatmap) return;
    const ranked = (heatmap.keys || [])
      .filter((key) => (Number(key.press_count) || 0) > 0)
      .sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0))
      .slice(0, KEY_CHOICES_LIMIT);
    const choices = ranked.map((key) => ({
      id: key.id,
      label: `${key.label} · ${formatCount(key.press_count)}`,
    }));
    // 用户从键盘视图带过来的选择可能不在高频榜里——保底追加，而不是悄悄换掉。
    if (current && !choices.some((choice) => choice.id === current)) {
      const known = (heatmap.keys || []).find((key) => key.id === current);
      choices.push({ id: current, label: (known && known.label) || current });
    }
    if (!choices.length) return; // 没有按键数据时保留现有选项，避免空下拉
    mount(
      keySelect,
      ...choices.map((choice) =>
        h('option', { value: choice.id, text: choice.label, selected: choice.id === current }),
      ),
    );
    if (!current && choices.length) {
      keySelect.value = choices[0].id;
      setState('selectedKeyId', choices[0].id);
    } else {
      keySelect.value = current;
    }
  }

  function renderKeySplit(state) {
    renderKeyChoices(state);
    const payload = state.data.insightKey;
    if (!payload) {
      if (state.loading.insightKey) mount(keySplitHost, skeletonRows(2));
      return;
    }
    const byApp = payload.by_app || [];
    const totals = payload.totals || {};
    if (!byApp.length) {
      mount(keySplitHost, emptyState({
        title: `${payload.key.label} 没有按应用拆分的数据`,
        detail: '这个键在本周期内没有被按下，或按键发生在无法识别前台应用的时段',
        mark: '·',
      }));
      return;
    }
    const top = Math.max(1, ...byApp.map((item) => Number(item.press_count) || 0));
    mount(
      keySplitHost,
      h('div', {
        class: 'text-sm muted',
        text: `${payload.key.label} 的 ${formatCount(totals.press_count || 0)} 次按下来自：`,
      }),
      ...byApp.slice(0, 10).map((item) =>
        h(
          'div',
          { class: 'top-key' },
          h('span', { class: 'rank' }),
          h('span', { class: 'truncate', text: item.display_name }),
          bar((Number(item.press_count) || 0) / top),
          h('span', { class: 'top-key__count', text: formatCount(item.press_count) }),
          h('span', { class: 'top-key__percent', text: formatPercent(item.percent) }),
        ),
      ),
    );
  }

  function reload() {
    const state = getState();
    for (const request of requestsFor(state)) {
      fetchInto(request.key, request.path, request.params);
    }
  }

  /** 周期切换后，已选键位可能在本周期一次都没被按——仍然查询它，让空态自己说明。 */
  function keyIdFor(state) {
    const heatmap = state.data.insightHeatmap;
    if (state.selectedKeyId) return state.selectedKeyId;
    if (heatmap && Array.isArray(heatmap.keys)) {
      const top = heatmap.keys
        .filter((key) => (Number(key.press_count) || 0) > 0)
        .sort((left, right) => (Number(right.press_count) || 0) - (Number(left.press_count) || 0))[0];
      if (top) return top.id;
    }
    return 'space';
  }

  /**
   * @param {Readonly<import('../core/store.js').State>} state
   * @returns {import('../types/api.js').DataRequest[]}
   */
  function requestsFor(state) {
    const period = periodParams(state.period);
    // "结论"归总览独占，因此这里不再取 /overview（14 文档 §2.9）——少一个请求。
    return [
      { key: 'insightKeyboard', path: '/insights/app-keyboard', params: { ...period, limit: 20 } },
      { key: 'insightRhythm', path: '/insights/rhythm', params: period },
      // top=10：图标带一行装得下十来个，取 5 会让 `+N` 把大半个下午都吞掉。
      { key: 'insightTimeline', path: '/usage/timeline', params: { ...period, top: 10 } },
      // 高频键选择器的数据源（M3-6 给出的两个方案之一：让洞察视图也取一次 heatmap）。
      { key: 'insightHeatmap', path: '/keyboard/heatmap', params: period },
      { key: 'insightKey', path: `/keyboard/keys/${keyIdFor(state)}`, params: period },
    ];
  }

  return {
    needs: requestsFor,
    /** 视图级筛选：键位选择改的是请求参数（14 文档 §4.1）。 */
    filters: () => [keySelect],
    render,
    destroy() {
      band.destroy();
      hourlyChart.destroy();
      rhythmChart.destroy();
      root.replaceChildren();
    },
  };
}
