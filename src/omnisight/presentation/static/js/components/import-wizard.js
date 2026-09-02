// 历史数据导入向导（09 文档 §2 的四步）+ 首页检测横幅。
//
// 不进路由：它是一次性流程，由横幅、设置抽屉或 data-action 打开。四步全部在
// 同一个抽屉里切换内容，关闭即取消轮询（导入本身在后台线程继续，关掉页面
// 也能续传——断点在服务端）。
import { get as apiGet, post as apiPost } from '../core/api.js';
import { h, mount } from '../core/dom.js';
import { drawer } from './drawer.js';
import { fail } from './toast.js';

const DISMISS_KEY = 'omnisight.importDismissed';
const PHASE_LABELS = {
  tl_sessions: '导入 TimeLens 应用使用记录',
  tl_keys: '导入 TimeLens 按键统计',
  kt_raw: '导入 KeyTrace 按键明细',
  finalize: '收尾',
};

/** 首页横幅：检测到旧库且从未导入/关闭过时显示（09 文档 §2.1，可关闭）。 */
export async function mountImportBanner(container) {
  if (!container) return;
  let status;
  try {
    status = await apiGet('/import/progress');
  } catch (error) {
    return; // 检测失败不影响启动
  }
  if (!status || status.state !== 'idle' || !status.available) return;
  if (localStorage.getItem(DISMISS_KEY) === '1') return;

  const close = h('button', { class: 'icon-button', type: 'button', text: '\u2715',
    attrs: { 'aria-label': '关闭提醒' },
    on: { click: () => { localStorage.setItem(DISMISS_KEY, '1'); banner.remove(); } } });
  const open = h('button', {
    class: 'button button--primary', type: 'button', text: '导入旧数据',
    on: { click: () => { banner.remove(); openImportWizard(); } },
  });
  const banner = h(
    'div',
    { class: 'banner banner--info', attrs: { role: 'status' } },
    h('div', { class: 'banner__body' },
      h('strong', { text: '发现旧版数据' }),
      h('span', { class: 'banner__detail', text: '检测到 TimeLens / KeyTrace 的历史数据库，可以导入到 OmniSight。' })),
    h('div', { class: 'banner__actions' }, open, close),
  );
  container.append(banner);
}

let wizardOpen = false;

export function openImportWizard() {
  if (wizardOpen) return;
  wizardOpen = true;
  const state = {
    step: 1,
    detected: [],
    selected: { timelens: null, keytrace: null },
    preview: null,
    status: null,
    report: null,
  };
  let pollTimer = 0;
  let instance = null;

  const closeWizard = () => {
    if (pollTimer) window.clearInterval(pollTimer);
    wizardOpen = false;
  };

  const body = h('div', { class: 'import-wizard' });
  const footer = h('div', { class: 'import-wizard__foot' });
  instance = drawer({
    title: '导入旧版数据',
    body,
    footer,
    onClose: closeWizard,
  });

  const rerender = () => {
    mount(body, stepNode(state, actions));
    mount(footer, footerNode(state, actions));
  };

  const actions = {
    async refreshDetected() {
      try {
        const payload = await apiGet('/import/detect');
        state.detected = payload.detected || [];
        for (const item of state.detected) {
          state.selected[item.kind] = state.selected[item.kind] || item.path;
        }
      } catch (error) {
        state.detected = [];
      }
      rerender();
    },
    toggle(kind, path, checked) {
      state.selected[kind] = checked ? path : null;
      rerender();
    },
    setManual(kind, value) {
      state.selected[kind] = value.trim() || null;
    },
    async toStep2() {
      if (!state.selected.timelens && !state.selected.keytrace) {
        fail('至少要选择一个旧数据库');
        return;
      }
      try {
        state.preview = await apiPost('/import/preview', { sources: state.selected });
        state.step = 2;
      } catch (error) {
        fail(error.message || '扫描旧数据库失败');
        return;
      }
      rerender();
    },
    back() {
      state.step -= 1;
      rerender();
    },
    async start() {
      try {
        state.status = await apiPost('/import/start', {
          sources: state.selected,
          losses: (state.preview && state.preview.losses) || [],
        });
        state.step = 3;
      } catch (error) {
        fail(error.message || '启动导入失败');
        return;
      }
      rerender();
      pollTimer = window.setInterval(actions.poll, 1200);
    },
    async poll() {
      try {
        state.status = await apiGet('/import/progress');
      } catch (error) {
        return;
      }
      if (!state.status.busy && state.status.state === 'done') {
        window.clearInterval(pollTimer);
        pollTimer = 0;
        try {
          state.report = await apiGet('/import/report');
        } catch (error) {
          state.report = null;
        }
        state.step = 4;
      } else if (!state.status.busy && state.status.error) {
        window.clearInterval(pollTimer);
        pollTimer = 0;
        fail(state.status.error);
      }
      rerender();
    },
    async pause() {
      try {
        state.status = await apiPost('/import/cancel');
      } catch (error) {
        fail(error.message || '暂停失败');
      }
      rerender();
    },
    close() {
      instance.close();
    },
    async undo() {
      try {
        await apiPost('/import/undo');
        fail('撤销已开始，历史数据将在后台清除');
      } catch (error) {
        fail(error.message || '撤销失败');
        return;
      }
      instance.close();
    },
  };

  actions.refreshDetected();
  rerender();
}

// ── 各步骤的渲染 ────────────────────────────────────────────────────────

function stepNode(state, actions) {
  if (state.step === 1) return step1(state, actions);
  if (state.step === 2) return step2(state, actions);
  if (state.step === 3) return step3(state, actions);
  return step4(state, actions);
}

/** 步骤 1/4：发现的数据。 */
function step1(state, actions) {
  const list = state.detected.length
    ? state.detected.map((item) => sourceRow(state, actions, item.kind, item))
    : [h('p', { class: 'muted', text: '默认位置没有找到旧数据库。请在下面输入旧库文件的完整路径。' })];
  return h('div', {},
    stepHeading(1, '发现的数据'),
    h('ul', { class: 'import-sources' }, list),
    h('details', { class: 'import-manual' },
      h('summary', { text: '选择其他位置…' }),
      manualField(state, actions, 'timelens', 'TimeLens usage.db 路径'),
      manualField(state, actions, 'keytrace', 'KeyTrace keytrace.sqlite3 路径')),
    h('p', { class: 'field__note',
      text: '旧库在整个过程中只读，不会被修改；导入前会自动备份到数据目录的 backup/ 下。' }));
}

function sourceRow(state, actions, kind, item) {
  const checked = state.selected[kind] === item.path;
  return h('li', { class: 'import-source' },
    h('label', { class: 'import-source__main' },
      h('input', { type: 'checkbox', checked,
        on: { change: (event) => actions.toggle(kind, item.path, event.target.checked) } }),
      h('span', {}, [
        h('strong', { text: kind === 'timelens' ? 'TimeLens' : 'KeyTrace' }),
        h('span', { class: 'import-source__path', text: item.path }),
        h('span', { class: 'import-source__meta',
          text: `${(item.size_bytes / 1048576).toFixed(1)} MB · 修改于 ${item.mtime}` }),
      ])));
}

function manualField(state, actions, kind, placeholder) {
  const input = h('input', {
    class: 'input', type: 'text', value: state.selected[kind] || '',
    attrs: { placeholder, spellcheck: 'false' },
    on: { input: (event) => actions.setManual(kind, event.target.value) },
  });
  return h('label', { class: 'field' },
    h('span', { class: 'field__label', text: kind === 'timelens' ? 'TimeLens 数据库' : 'KeyTrace 数据库' }),
    input);
}

/** 步骤 2/4：将会丢失什么——整个向导的重点（09 文档 §2.2）。 */
function step2(state, actions) {
  const preview = state.preview || {};
  const tl = preview.timelens || {};
  const kt = preview.keytrace || {};
  const losses = preview.losses || [];
  const stats = [];
  if (tl.sessions) {
    stats.push(`应用使用记录 ${tl.sessions.rows} 条（${tl.sessions.date_min} 起）`);
  }
  if (tl.key_usage) {
    stats.push(`按键统计 ${tl.key_usage.presses} 次（仅次数，无时长与归因）`);
  }
  if (kt.raw) {
    stats.push(`按键明细 ${kt.raw.rows} 条`);
  }
  return h('div', {},
    stepHeading(2, '将会丢失什么'),
    stats.length ? h('p', { text: '将导入：' + stats.join('；') }) : null,
    losses.length
      ? h('ul', { class: 'import-losses' },
          losses.map((loss) => h('li', {},
            h('span', { class: 'import-losses__mark', text: '⚠' }),
            h('span', { text: loss }))))
      : h('p', { class: 'muted', text: '没有发现数据损失。' }),
    (preview.conflict_days || []).length
      ? h('p', { class: 'field__note',
          text: `重叠日期以 KeyTrace 为准：${preview.conflict_days.length} 天将跳过 TimeLens 的按键计数。` })
      : null,
    h('p', { class: 'field__note',
      text: '从今天起记录的新数据不受任何影响。' }));
}

/** 步骤 3/4：正在导入。 */
function step3(state, actions) {
  const status = state.status || {};
  const counts = status.counts || {};
  const phase = PHASE_LABELS[status.phase] || status.phase || '';
  const parts = [];
  if (counts.sessions_imported) parts.push(`使用记录 ${counts.sessions_imported} 条`);
  if (counts.key_presses) parts.push(`按键次数 ${counts.key_presses}`);
  if (counts.raw_imported) parts.push(`按键明细 ${counts.raw_imported} 条`);
  const paused = status.state === 'paused';
  return h('div', {},
    stepHeading(3, paused ? '已暂停' : '正在导入'),
    h('div', { class: 'import-progress' },
      h('div', { class: 'import-progress__bar', attrs: { role: 'progressbar' } },
        h('div', { class: 'import-progress__fill' })),
      h('p', { text: phase }),
      parts.length ? h('p', { class: 'import-progress__counts', text: parts.join(' · ') }) : null,
      paused
        ? h('p', { class: 'field__note', text: '导入已暂停，点击"继续"从断点恢复。' })
        : null),
    h('p', { class: 'field__note',
      text: '可以关闭此窗口，导入在后台继续；中断后再次导入会从断点续传，不会产生重复。' }));
}

/** 步骤 4/4：完成报告。 */
function step4(state, actions) {
  const report = state.report || {};
  const sessions = report.sessions || {};
  const raw = report.raw_events || {};
  const usage = report.key_usage || {};
  const unmapped = report.unmapped_keys || {};
  const rows = [
    ['应用使用记录', `${sessions.imported || 0} 条`, sessions.date_range && sessions.date_range[0] ? `${sessions.date_range[0]} 起` : ''],
    ['按键明细', `${raw.imported || 0} 条`, raw.days ? `${raw.days} 天` : ''],
    ['按键次数（无时长）', `${usage.presses || 0} 次`, usage.days ? `${usage.days} 天` : ''],
    ['跳过（日期重叠）', `${(report.skipped_days || []).length} 天`, ''],
    ['未能映射的键', Object.keys(unmapped).length ? `${Object.keys(unmapped).length} 个：${Object.keys(unmapped).join('、')}` : '无', ''],
  ];
  return h('div', {},
    stepHeading(4, '导入完成'),
    h('table', { class: 'table import-report' },
      h('tbody', {}, rows.map(([name, value, note]) => h('tr', {},
        h('td', { text: name }), h('td', { text: value }), h('td', { class: 'muted', text: note }))))),
    (report.losses || []).length
      ? h('details', { class: 'import-losses import-losses--summary' },
          h('summary', { text: '有损说明（导入时已知悉）' }),
          h('ul', {}, (report.losses || []).map((loss) => h('li', { text: loss }))))
      : null,
    h('p', { class: 'field__note',
      text: `完整报告：${report.backup_dir || '数据目录'}/../import-report.json。旧数据文件未被修改。` }));
}

function stepHeading(step, title) {
  return h('h3', { class: 'import-wizard__title' },
    h('span', { class: 'import-wizard__step', text: `步骤 ${step}/4` }),
    h('span', { text: ` · ${title}` }));
}

function footerNode(state, actions) {
  if (state.step === 1) {
    return h('button', { class: 'button button--primary', type: 'button', text: '下一步',
      on: { click: actions.toStep2 } });
  }
  if (state.step === 2) {
    return h('div', { class: 'import-wizard__foot-row' },
      h('button', { class: 'button', type: 'button', text: '上一步', on: { click: actions.back } }),
      h('button', { class: 'button button--primary', type: 'button', text: '我知道了，开始导入',
        on: { click: actions.start } }));
  }
  if (state.step === 3) {
    const paused = state.status && state.status.state === 'paused';
    return h('button', { class: 'button', type: 'button', text: paused ? '继续' : '暂停',
      on: { click: paused ? actions.start : actions.pause } });
  }
  return h('div', { class: 'import-wizard__foot-row' },
    h('button', { class: 'button button--danger', type: 'button', text: '撤销导入',
      attrs: { title: '删除导入的历史数据；新采集的数据保留' },
      on: { click: () => {
        if (window.confirm('撤销将删除导入的历史数据（新采集的数据保留）。确定？')) actions.undo();
      } } }),
    h('span', { class: 'spacer' }),
    h('button', { class: 'button button--primary', type: 'button', text: '开始使用',
      on: { click: actions.close } }));
}
