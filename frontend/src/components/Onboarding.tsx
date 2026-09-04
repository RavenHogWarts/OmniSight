// 首次运行说明（08 文档 §6.1）。一屏读完的事实，不是 EULA 式的长文。
//
// 三条设计约束：
//   1. **内容全部来自后端**。"记录什么 / 不记录什么"两张清单由后端按当前能力与配置
//      算出来，前端只负责排版——写死在前端就等于承诺一件自己无从保证的事。
//   2. **它不是可以随手划掉的横幅**。首次运行必须点"开始使用"才关闭（那一下就是
//      `POST /onboarding/ack`），因此用 scrim + 对话框而不是 banner。
//   3. **之后仍然找得到**。托盘「关于与隐私说明」与 URL 的 `#about` 都会重新打开它，
//      此时它是普通对话框，Esc 与遮罩点击都能关。
import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { get as apiGet, post as apiPost } from '../core/api.ts';
import { closeOverlay, openOverlay } from './Drawer.tsx';
import { fail } from './toast.tsx';
import type { OnboardingRecord, OnboardingResponse } from '../types/api.d.ts';

/** 首屏调用：只在后端说 `required` 时弹出。取数失败一律安静跳过，不挡住仪表盘。 */
export async function maybeShowOnboarding(): Promise<void> {
  let payload: OnboardingResponse | null = null;
  try {
    payload = (await apiGet('/onboarding')) as OnboardingResponse;
  } catch {
    return;
  }
  if (!payload?.required) return;
  openOverlay(<Onboarding payload={payload} mandatory />);
}

/** 托盘「关于与隐私说明」与 `#about` 的入口：随时可看，随时可关。 */
export async function openAbout(): Promise<void> {
  try {
    const payload = (await apiGet('/onboarding')) as OnboardingResponse;
    openOverlay(<Onboarding payload={payload} mandatory={false} />);
  } catch {
    fail('无法读取隐私说明');
  }
}

export function Onboarding({
  payload,
  mandatory = false,
}: {
  payload: OnboardingResponse;
  mandatory?: boolean;
}) {
  const dialog = useRef<HTMLDivElement | null>(null);
  const opener = useRef<HTMLElement | null>(
    typeof document === 'undefined' ? null : (document.activeElement as HTMLElement | null),
  );

  const close = () => {
    closeOverlay();
    const previous = opener.current;
    if (previous && typeof previous.focus === 'function') previous.focus();
  };
  const closeRef = useRef(close);
  closeRef.current = close;

  useEffect(() => {
    const root = dialog.current;
    root?.querySelector<HTMLElement>('button')?.focus() ?? root?.focus();
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !mandatory) {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== 'Tab') return;
      const host = dialog.current;
      if (!host) return;
      const items = [...host.querySelectorAll<HTMLElement>('button, a[href]')].filter(
        (node) => node.offsetParent !== null,
      );
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      } else if (!host.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeydown, true);
    return () => document.removeEventListener('keydown', onKeydown, true);
  }, [mandatory]);

  const accept = async () => {
    if (mandatory) {
      try {
        await apiPost('/onboarding/ack', {});
      } catch {
        // 记不住也让用户进得去——下次再问一遍，比把人锁在门外好。
        fail('无法记录你的确认，下次启动可能再次显示这份说明');
      }
    }
    close();
  };

  const platform = payload.platform || {};
  const paths = payload.paths || {};
  const pause = payload.pause || {};

  return (
    <>
      {/* 遮罩点击只在非强制时关闭：首次运行必须走完"我看到了"这一步。 */}
      <div className="scrim" onClick={mandatory ? undefined : close} />
      <div
        className="onboarding"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
        tabIndex={-1}
      >
        <div className="onboarding__head">
          <h2 id="onboarding-title">{mandatory ? 'OmniSight 记录什么' : '关于与隐私说明'}</h2>
          <p className="muted">本机运行，无账号、不联网、无遥测。</p>
        </div>

        <div className="onboarding__lists">
          <FactList title="会记录" items={payload.records} itemClass="onboarding__item--yes" mark="✓" />
          <FactList title="不记录" items={payload.not_records} itemClass="onboarding__item--no" mark="✗" />
        </div>

        {/* 平台承诺（12 文档 M6 判据 5）：这句话必须出现，且不暗示已支持跨平台。 */}
        <div className="onboarding__notice" role="note">
          <strong>平台支持</strong>
          <p>{platform.notice || ''}</p>
          {platform.tier_label ? <p className="muted">{platform.tier_label}</p> : null}
        </div>

        <div className="onboarding__section">
          <h3>数据在哪</h3>
          <PathRow label="数据库" value={paths.database} />
          <PathRow label="数据目录" value={paths.data_dir} />
          <PathRow label="日志目录" value={paths.logs_dir} />
          <PathRow label="配置文件" value={paths.config} />
          <p className="muted">
            托盘菜单里的「打开数据目录」直接跳到这里；卸载时删掉它就没有残留。
          </p>
        </div>

        <div className="onboarding__section">
          <h3>如何暂停</h3>
          <p>{pause.detail || ''}</p>
        </div>

        <div className="onboarding__foot">
          <button className="button button--primary" type="button" onClick={accept}>
            {mandatory ? '开始使用' : '知道了'}
          </button>
          {mandatory ? (
            <button
              className="button"
              type="button"
              title="这份说明会在下次启动时再次出现"
              onClick={close}
            >
              稍后再说
            </button>
          ) : null}
        </div>
      </div>
    </>
  );
}

function FactList({
  title,
  items,
  itemClass,
  mark,
}: {
  title: string;
  items: readonly OnboardingRecord[] | undefined;
  itemClass: string;
  mark: ReactNode;
}) {
  return (
    <section className="onboarding__list">
      <h3>{title}</h3>
      <ul>
        {(items || []).map((item, index) => (
          <li className={`onboarding__item ${itemClass}`} key={index}>
            <span className="onboarding__mark" aria-hidden="true">
              {mark}
            </span>
            <div>
              <span>{item.text || ''}</span>
              {item.detail ? <p className="muted">{item.detail}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function PathRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null;
  return (
    <div className="onboarding__path">
      <span className="onboarding__path-label">{label}</span>
      {/* 路径用 code 而不是普通文本：Windows 路径里的反斜杠在等宽字体下才不易读错。 */}
      <code>{value}</code>
    </div>
  );
}
