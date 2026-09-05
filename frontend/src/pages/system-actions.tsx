// 进程级动作（18 文档 批 5）：重新启动、退出、打开目录。三件事都只有后端做得到。
//
// **重启与退出各有一个不能糊弄的失败模式。** 重启是"新实例起不来而旧实例已经退了"——用户
// 只剩一个消失的托盘图标，因此后端先确认新进程活着再停机（`core/lifecycle.restart`）。退出
// 是它真的停掉采集，因此除了确认对话框，页面上不留第二个入口。
//
// **重启之后令牌不变**：接班实例继承 `runtime.json` 里那一个（见 `presentation/security.py`
// 的说明）。因此这一页只要等新实例应答就能原地刷新，不必让用户回托盘重开一遍——那是三个
// 前身版本里最招人烦的一步。
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { closeOverlay, openOverlay } from '../components/Drawer.tsx';
import { confirmDialog } from '../components/Confirm.tsx';
import { fail } from '../components/toast.tsx';
import { ApiError, get as apiGet, messageOf, post } from '../core/api.ts';
import { getState } from '../core/store.ts';
import type { StatusResponse } from '../types/api.d.ts';

/** 探活走免令牌的 `/healthz`（它只回一个字面量，见 web.py）。 */
async function healthy(): Promise<boolean> {
  try {
    const response = await fetch('/healthz', { cache: 'no-store', credentials: 'omit' });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * 等到**另一个实例**在应答。
 *
 * 判据是 `/api/v1/status` 的 `started_at` 变了，而不是"端口上有人应答"——后者分不出新旧，
 * 而旧实例在收到重启请求之后还要活一小会儿（响应先出门，停机排在 0.4 秒后的线程里）。
 * 原先的写法是"先等它下线、再等它上线"，而整个下线窗口可能落在两次轮询之间：那时页面会
 * 立刻刷新，刷到的是正在拆自己的旧实例。
 *
 * 401 是另一种结局：接班实例换了令牌（继承那一步没成，见 `core/lifecycle._claim_session`），
 * 这一页手里那份从此无效。**这时不能刷新**——刷出来是一个连不上数据的空壳，而用户需要知道
 * 该回托盘重新打开。
 */
async function nextInstance(before: string): Promise<'ready' | 'token' | 'timeout'> {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    try {
      const status = (await apiGet('/status')) as StatusResponse;
      if (String(status.started_at || '') !== before) return 'ready';
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return 'token';
      // 其余是连接被拒：旧实例正在下线、新实例还没起来。继续等。
    }
    await new Promise((resolve) => window.setTimeout(resolve, 500));
  }
  return 'timeout';
}

/** 轮询到条件成立或超时。@returns 成立了吗 */
async function until(condition: () => Promise<boolean>, timeoutMs: number): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await condition()) return true;
    await new Promise((resolve) => window.setTimeout(resolve, 400));
  }
  return false;
}

export async function restartApp(): Promise<void> {
  const agreed = await confirmDialog({
    title: '重新启动 OmniSight？',
    detail: '采集会中断几秒，然后自动继续。需重启才生效的设置会在这次启动时生效。',
    confirmLabel: '重新启动',
  });
  if (!agreed) return;
  try {
    await post('/system/restart', {});
  } catch (error) {
    fail(messageOf(error, '重启请求失败'));
    return;
  }
  openOverlay(<Restarting />);
}

export async function quitApp(): Promise<void> {
  const agreed = await confirmDialog({
    title: '退出 OmniSight？',
    detail: '退出后不再记录任何按键与前台时长，直到你手动重新启动它。',
    confirmLabel: '退出',
    danger: true,
  });
  if (!agreed) return;
  try {
    await post('/system/quit', {});
  } catch (error) {
    fail(messageOf(error, '退出请求失败'));
    return;
  }
  openOverlay(<Stopping />);
}

/** 打开数据目录 / 日志目录。后端负责"管理员模式下降权打开"（lifecycle._open_external）。 */
export function RevealButton({ target, label }: { target: 'data' | 'logs'; label: string }) {
  return (
    <button
      className="button"
      type="button"
      onClick={async () => {
        try {
          await post('/system/reveal', { target });
        } catch (error) {
          fail(messageOf(error, '打开目录失败'));
        }
      }}
    >
      {label}
    </button>
  );
}

/**
 * 「正在重启」。等的是"另一个实例在应答"（见 `nextInstance`），不是"端口通了"。
 *
 * `started_at` 读的是本页启动时那一份状态。读不到时（状态本来就没取到）退回旧办法：先等
 * 它下线，再等它上线——那时无从分辨新旧，但至少不会在旧实例还在应答时就刷新。
 */
function Restarting() {
  const [phase, setPhase] = useState<'wait' | 'failed' | 'token'>('wait');
  useEffect(() => {
    let cancelled = false;
    const before = String(getState().status?.started_at || '');
    void (async () => {
      if (!before) await until(async () => !(await healthy()), 15000);
      const outcome = await nextInstance(before);
      if (cancelled) return;
      if (outcome === 'ready') window.location.reload();
      else setPhase(outcome === 'token' ? 'token' : 'failed');
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (phase === 'token') {
    return (
      <Blocker
        title="重启完成，但令牌要重新交接"
        detail="接班实例换用了新的访问令牌，这一页手里那份已经失效。请从托盘菜单重新打开仪表盘——刷新这一页只会得到一个读不到数据的外壳。"
        action={
          <button className="button" type="button" onClick={() => closeOverlay()}>
            知道了
          </button>
        }
      />
    );
  }
  if (phase === 'failed') {
    return (
      <Blocker
        title="没等到新实例应答"
        detail="它可能仍在启动，也可能启动失败。请查看日志目录里的 STARTUP_ERROR.txt，或从桌面图标重新打开。"
        action={
          <button className="button button--primary" type="button" onClick={() => closeOverlay()}>
            知道了
          </button>
        }
      />
    );
  }
  return <Blocker title="正在重启…" detail="等新实例接手后这一页会自动刷新。" spinner />;
}

/** 「已退出」。不刷新页面：刷新只会得到一个连不上的外壳。 */
function Stopping() {
  const [done, setDone] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const down = await until(async () => !(await healthy()), 20000);
      if (!cancelled && down) setDone(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);
  return done ? (
    <Blocker
      title="OmniSight 已退出"
      detail="采集已停止。从开始菜单或桌面图标可以重新启动它；这个标签页可以关掉了。"
    />
  ) : (
    <Blocker title="正在退出…" spinner />
  );
}

/** 挡住整页的一张卡。重启与退出期间点什么都没有意义，因此不给关闭入口（除非传 action）。 */
function Blocker({
  title,
  detail,
  spinner = false,
  action,
}: {
  title: string;
  detail?: string;
  spinner?: boolean;
  action?: ReactNode;
}) {
  return (
    <>
      <div className="scrim" />
      <div className="confirm" role="alertdialog" aria-live="assertive" aria-label={title}>
        <h2>{title}</h2>
        {detail ? <p className="muted">{detail}</p> : null}
        {spinner ? <div className="veil__spinner" /> : null}
        {action ? <div className="confirm__foot">{action}</div> : null}
      </div>
    </>
  );
}

/** 设置页底部那一段。两个动作各自确认，措辞里说清代价。 */
export function ProcessActions() {
  return (
    <div className="actions">
      <button className="button" type="button" onClick={() => void restartApp()}>
        重新启动…
      </button>
      <button className="button button--danger" type="button" onClick={() => void quitApp()}>
        退出 OmniSight…
      </button>
    </div>
  );
}
