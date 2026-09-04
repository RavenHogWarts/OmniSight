// 历史数据导入向导（09 文档 §2 的四步）+ 首页检测横幅。
//
// 不进路由：它是一次性流程，由横幅、设置抽屉或顶栏动作打开。四步全部在同一个抽屉里
// 切换内容，关闭即取消轮询（导入本身在后台线程继续，关掉页面也能续传——断点在服务端）。
//
// 向导的四步共享一份**组件内**状态。它不进 store：一次性流程，关掉抽屉就结束，放进
// 全局状态只会多一份要清理的东西（07 文档 §4.1 第 1 条的同一条道理）。
import { useEffect, useRef, useState } from 'react';
import { get as apiGet, messageOf, post as apiPost } from '../core/api.ts';
import { Drawer, closeOverlay, openOverlay } from './Drawer.tsx';
import { Icon } from './Icon.tsx';
import { fail } from './toast.tsx';
import type {
  ImportPreviewResponse,
  ImportProgressResponse,
  ImportReportResponse,
  LegacySelection,
  LegacySource,
} from '../types/api.d.ts';

const DISMISS_KEY = 'omnisight.importDismissed';
const PHASE_LABELS: Record<string, string> = {
  tl_sessions: '导入 TimeLens 应用使用记录',
  tl_keys: '导入 TimeLens 按键统计',
  kt_raw: '导入 KeyTrace 按键明细',
  finalize: '收尾',
};

type Kind = 'timelens' | 'keytrace';

export function openImportWizard(): void {
  openOverlay(
    <Drawer title="导入旧版数据">
      <ImportWizard />
    </Drawer>,
  );
}

/**
 * 首页横幅：检测到旧库且从未导入/关闭过时显示（09 文档 §2.1，可关闭）。
 *
 * 检测不阻塞启动，所以它自己在挂载后异步问一次；失败一律安静跳过。
 */
export function ImportBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISS_KEY) === '1') return;
    let cancelled = false;
    (async () => {
      try {
        const status = (await apiGet('/import/progress')) as ImportProgressResponse | null;
        if (cancelled) return;
        if (status && status.state === 'idle' && status.available) setVisible(true);
      } catch {
        // 检测失败不影响启动
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!visible) return null;
  return (
    <div className="banner banner--info" role="status">
      <div className="banner__body">
        <strong>发现旧版数据</strong>
        <span className="banner__detail">
          检测到 TimeLens / KeyTrace 的历史数据库，可以导入到 OmniSight。
        </span>
      </div>
      <div className="banner__actions">
        <button
          className="button button--primary"
          type="button"
          onClick={() => {
            setVisible(false);
            openImportWizard();
          }}
        >
          导入旧数据
        </button>
        <button
          className="icon-button"
          type="button"
          aria-label="关闭提醒"
          onClick={() => {
            localStorage.setItem(DISMISS_KEY, '1');
            setVisible(false);
          }}
        >
          <Icon name="close" />
        </button>
      </div>
    </div>
  );
}

function ImportWizard() {
  const [step, setStep] = useState(1);
  const [detected, setDetected] = useState<readonly LegacySource[]>([]);
  const [selected, setSelected] = useState<LegacySelection>({ timelens: null, keytrace: null });
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [status, setStatus] = useState<ImportProgressResponse | null>(null);
  const [report, setReport] = useState<ImportReportResponse | null>(null);
  const timer = useRef(0);

  // 关掉抽屉就停轮询。导入本身在后台线程继续，因此这里只是不再问了。
  useEffect(() => () => window.clearInterval(timer.current), []);

  useEffect(() => {
    (async () => {
      try {
        const payload = (await apiGet('/import/detect')) as { detected?: LegacySource[] };
        const list = payload?.detected || [];
        setDetected(list);
        setSelected((current) => {
          const next = { ...current };
          for (const item of list) {
            const kind = item.kind as Kind;
            next[kind] = next[kind] || item.path;
          }
          return next;
        });
      } catch {
        setDetected([]);
      }
    })();
  }, []);

  const toStep2 = async () => {
    if (!selected.timelens && !selected.keytrace) {
      fail('至少要选择一个旧数据库');
      return;
    }
    try {
      setPreview((await apiPost('/import/preview', { sources: selected })) as ImportPreviewResponse);
      setStep(2);
    } catch (error) {
      fail(messageOf(error, '扫描旧数据库失败'));
    }
  };

  const poll = async () => {
    let next: ImportProgressResponse | null = null;
    try {
      next = (await apiGet('/import/progress')) as ImportProgressResponse;
    } catch {
      return;
    }
    if (!next) return;
    setStatus(next);
    if (!next.busy && next.state === 'done') {
      window.clearInterval(timer.current);
      timer.current = 0;
      try {
        setReport((await apiGet('/import/report')) as ImportReportResponse);
      } catch {
        setReport(null);
      }
      setStep(4);
    } else if (!next.busy && next.error) {
      window.clearInterval(timer.current);
      timer.current = 0;
      fail(next.error);
    }
  };

  const start = async () => {
    try {
      setStatus(
        (await apiPost('/import/start', {
          sources: selected,
          losses: preview?.losses || [],
        })) as ImportProgressResponse,
      );
      setStep(3);
    } catch (error) {
      fail(messageOf(error, '启动导入失败'));
      return;
    }
    window.clearInterval(timer.current);
    timer.current = window.setInterval(poll, 1200);
  };

  const pause = async () => {
    try {
      setStatus((await apiPost('/import/cancel')) as ImportProgressResponse);
    } catch (error) {
      fail(messageOf(error, '暂停失败'));
    }
  };

  const undo = async () => {
    try {
      await apiPost('/import/undo');
      fail('撤销已开始，历史数据将在后台清除');
    } catch (error) {
      fail(messageOf(error, '撤销失败'));
      return;
    }
    closeOverlay();
  };

  return (
    <>
      <div className="import-wizard">
        {step === 1 ? (
          <Step1 detected={detected} selected={selected} onChange={setSelected} />
        ) : null}
        {step === 2 ? <Step2 preview={preview} /> : null}
        {step === 3 ? <Step3 status={status} /> : null}
        {step === 4 ? <Step4 report={report} /> : null}
      </div>
      <div className="import-wizard__foot">
        <Footer
          step={step}
          paused={status?.state === 'paused'}
          onNext={toStep2}
          onBack={() => setStep((value) => value - 1)}
          onStart={start}
          onPause={pause}
          onUndo={undo}
        />
      </div>
    </>
  );
}

function StepHeading({ step, title }: { step: number; title: string }) {
  return (
    <h3 className="import-wizard__title">
      <span className="import-wizard__step">步骤 {step}/4</span>
      <span> · {title}</span>
    </h3>
  );
}

/** 步骤 1/4：发现的数据。 */
function Step1({
  detected,
  selected,
  onChange,
}: {
  detected: readonly LegacySource[];
  selected: LegacySelection;
  onChange: (next: LegacySelection) => void;
}) {
  const toggle = (kind: Kind, path: string, checked: boolean) =>
    onChange({ ...selected, [kind]: checked ? path : null });
  const setManual = (kind: Kind, value: string) =>
    onChange({ ...selected, [kind]: value.trim() || null });

  return (
    <div>
      <StepHeading step={1} title="发现的数据" />
      <ul className="import-sources">
        {detected.length ? (
          detected.map((item) => (
            <li className="import-source" key={item.path}>
              <label className="import-source__main">
                <input
                  type="checkbox"
                  checked={selected[item.kind as Kind] === item.path}
                  onChange={(event) => toggle(item.kind as Kind, item.path, event.target.checked)}
                />
                <span>
                  <strong>{item.kind === 'timelens' ? 'TimeLens' : 'KeyTrace'}</strong>
                  <span className="import-source__path">{item.path}</span>
                  <span className="import-source__meta">
                    {(item.size_bytes / 1048576).toFixed(1)} MB · 修改于 {item.mtime}
                  </span>
                </span>
              </label>
            </li>
          ))
        ) : (
          <p className="muted">默认位置没有找到旧数据库。请在下面输入旧库文件的完整路径。</p>
        )}
      </ul>
      <details className="import-manual">
        <summary>选择其他位置…</summary>
        <ManualField
          kind="timelens"
          value={selected.timelens}
          placeholder="TimeLens usage.db 路径"
          onChange={setManual}
        />
        <ManualField
          kind="keytrace"
          value={selected.keytrace}
          placeholder="KeyTrace keytrace.sqlite3 路径"
          onChange={setManual}
        />
      </details>
      <p className="field__note">
        旧库在整个过程中只读，不会被修改；导入前会自动备份到数据目录的 backup/ 下。
      </p>
    </div>
  );
}

function ManualField({
  kind,
  value,
  placeholder,
  onChange,
}: {
  kind: Kind;
  value: string | null;
  placeholder: string;
  onChange: (kind: Kind, value: string) => void;
}) {
  return (
    <label className="field">
      <span className="field__label">
        {kind === 'timelens' ? 'TimeLens 数据库' : 'KeyTrace 数据库'}
      </span>
      <input
        className="input"
        type="text"
        value={value || ''}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(event) => onChange(kind, event.target.value)}
      />
    </label>
  );
}

/** 步骤 2/4：将会丢失什么——整个向导的重点（09 文档 §2.2）。 */
function Step2({ preview }: { preview: ImportPreviewResponse | null }) {
  const tl = preview?.timelens;
  const kt = preview?.keytrace;
  const losses = preview?.losses || [];
  const conflicts = preview?.conflict_days || [];
  const stats: string[] = [];
  if (tl?.sessions) stats.push(`应用使用记录 ${tl.sessions.rows} 条（${tl.sessions.date_min} 起）`);
  if (tl?.key_usage) stats.push(`按键统计 ${tl.key_usage.presses} 次（仅次数，无时长与归因）`);
  if (kt?.raw) stats.push(`按键明细 ${kt.raw.rows} 条`);

  return (
    <div>
      <StepHeading step={2} title="将会丢失什么" />
      {stats.length ? <p>将导入：{stats.join('；')}</p> : null}
      {losses.length ? (
        <ul className="import-losses">
          {losses.map((loss) => (
            <li key={loss}>
              <span className="import-losses__mark">⚠</span>
              <span>{loss}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">没有发现数据损失。</p>
      )}
      {conflicts.length ? (
        <p className="field__note">
          重叠日期以 KeyTrace 为准：{conflicts.length} 天将跳过 TimeLens 的按键计数。
        </p>
      ) : null}
      <p className="field__note">从今天起记录的新数据不受任何影响。</p>
    </div>
  );
}

/** 步骤 3/4：正在导入。 */
function Step3({ status }: { status: ImportProgressResponse | null }) {
  const counts = status?.counts;
  const phase = PHASE_LABELS[status?.phase || ''] || status?.phase || '';
  const paused = status?.state === 'paused';
  const parts: string[] = [];
  if (counts?.sessions_imported) parts.push(`使用记录 ${counts.sessions_imported} 条`);
  if (counts?.key_presses) parts.push(`按键次数 ${counts.key_presses}`);
  if (counts?.raw_imported) parts.push(`按键明细 ${counts.raw_imported} 条`);

  return (
    <div>
      <StepHeading step={3} title={paused ? '已暂停' : '正在导入'} />
      <div className="import-progress">
        <div className="import-progress__bar" role="progressbar">
          <div className="import-progress__fill" />
        </div>
        <p>{phase}</p>
        {parts.length ? <p className="import-progress__counts">{parts.join(' · ')}</p> : null}
        {paused ? <p className="field__note">导入已暂停，点击"继续"从断点恢复。</p> : null}
      </div>
      <p className="field__note">
        可以关闭此窗口，导入在后台继续；中断后再次导入会从断点续传，不会产生重复。
      </p>
    </div>
  );
}

/** 步骤 4/4：完成报告。 */
function Step4({ report }: { report: ImportReportResponse | null }) {
  const sessions = report?.sessions;
  const raw = report?.raw_events;
  const usage = report?.key_usage;
  const unmapped = report?.unmapped_keys || {};
  const unmappedKeys = Object.keys(unmapped);
  const rows: readonly (readonly [string, string, string])[] = [
    [
      '应用使用记录',
      `${sessions?.imported || 0} 条`,
      sessions?.date_range?.[0] ? `${sessions.date_range[0]} 起` : '',
    ],
    ['按键明细', `${raw?.imported || 0} 条`, raw?.days ? `${raw.days} 天` : ''],
    ['按键次数（无时长）', `${usage?.presses || 0} 次`, usage?.days ? `${usage.days} 天` : ''],
    ['跳过（日期重叠）', `${(report?.skipped_days || []).length} 天`, ''],
    [
      '未能映射的键',
      unmappedKeys.length ? `${unmappedKeys.length} 个：${unmappedKeys.join('、')}` : '无',
      '',
    ],
  ];

  return (
    <div>
      <StepHeading step={4} title="导入完成" />
      <table className="table import-report">
        <tbody>
          {rows.map(([name, value, note]) => (
            <tr key={name}>
              <td>{name}</td>
              <td>{value}</td>
              <td className="muted">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {(report?.losses || []).length ? (
        <details className="import-losses import-losses--summary">
          <summary>有损说明（导入时已知悉）</summary>
          <ul>
            {(report?.losses || []).map((loss) => (
              <li key={loss}>{loss}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <p className="field__note">
        完整报告：{report?.backup_dir || '数据目录'}/../import-report.json。旧数据文件未被修改。
      </p>
    </div>
  );
}

function Footer({
  step,
  paused,
  onNext,
  onBack,
  onStart,
  onPause,
  onUndo,
}: {
  step: number;
  paused: boolean;
  onNext: () => void;
  onBack: () => void;
  onStart: () => void;
  onPause: () => void;
  onUndo: () => void;
}) {
  if (step === 1) {
    return (
      <button className="button button--primary" type="button" onClick={onNext}>
        下一步
      </button>
    );
  }
  if (step === 2) {
    return (
      <div className="import-wizard__foot-row">
        <button className="button" type="button" onClick={onBack}>
          上一步
        </button>
        <button className="button button--primary" type="button" onClick={onStart}>
          我知道了，开始导入
        </button>
      </div>
    );
  }
  if (step === 3) {
    return (
      <button className="button" type="button" onClick={paused ? onStart : onPause}>
        {paused ? '继续' : '暂停'}
      </button>
    );
  }
  return (
    <div className="import-wizard__foot-row">
      <button
        className="button button--danger"
        type="button"
        title="删除导入的历史数据；新采集的数据保留"
        onClick={() => {
          if (window.confirm('撤销将删除导入的历史数据（新采集的数据保留）。确定？')) onUndo();
        }}
      >
        撤销导入
      </button>
      <span className="spacer" />
      <button className="button button--primary" type="button" onClick={() => closeOverlay()}>
        开始使用
      </button>
    </div>
  );
}
