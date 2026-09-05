// 首次运行说明（08 文档 §6.1）。一屏读完的事实，不是 EULA 式的长文。
//
// 原先三条设计约束，现在两条在这里、一条搬走了：
//   1. **内容全部来自后端**——"记录什么 / 不记录什么"两张清单由后端按当前能力与配置算出来。
//      排版在 components/AboutContent.tsx，因为同一份内容还要给 `/about` 那一页用。
//   2. **它不是可以随手划掉的横幅**。首次运行必须点「开始使用」才关闭（那一下就是
//      `POST /onboarding/ack`），因此用 scrim + 对话框而不是 banner。
//   3. ~~之后仍然找得到~~ → 18 文档 批 4：那件事现在由 `/about` 页面负责（托盘与设置页都
//      指向它）。**因此这个文件只剩首启那一次**，没有"随手看看"的非强制分支：Esc 与点遮罩
//      都不关它，`openAbout()` 这个导出也没有了。
import { useEffect, useRef } from 'react';
import { AboutContent } from './AboutContent.tsx';
import { closeOverlay, openOverlay } from './Drawer.tsx';
import { fail } from './toast.tsx';
import { get as apiGet, post as apiPost } from '../core/api.ts';
import type { OnboardingResponse } from '../types/api.d.ts';

/** 首屏调用：只在后端说 `required` 时弹出。取数失败一律安静跳过，不挡住仪表盘。 */
export async function maybeShowOnboarding(): Promise<void> {
  let payload: OnboardingResponse | null = null;
  try {
    payload = (await apiGet('/onboarding')) as OnboardingResponse;
  } catch {
    return;
  }
  if (!payload?.required) return;
  openOverlay(<Onboarding payload={payload} />);
}

export function Onboarding({ payload }: { payload: OnboardingResponse }) {
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
    // 焦点陷阱，没有 Esc 分支：这一次是必须走完的一步（08 文档 §6.1）。
    const onKeydown = (event: KeyboardEvent) => {
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
  }, []);

  const accept = async () => {
    try {
      await apiPost('/onboarding/ack', {});
    } catch {
      // 记不住也让用户进得去——下次再问一遍，比把人锁在门外好。
      fail('无法记录你的确认，下次启动可能再次显示这份说明');
    }
    close();
  };

  return (
    <>
      {/* 遮罩不可点关：首次运行必须走完"我看到了"这一步。 */}
      <div className="scrim" />
      <div
        className="onboarding"
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
        tabIndex={-1}
      >
        <div className="onboarding__head">
          <h2 id="onboarding-title">OmniSight 记录什么</h2>
          <p className="muted">本机运行，无账号、不联网、无遥测。</p>
        </div>

        <AboutContent payload={payload} />

        <div className="onboarding__foot">
          <button className="button button--primary" type="button" onClick={() => void accept()}>
            开始使用
          </button>
          <button
            className="button"
            type="button"
            title="这份说明会在下次启动时再次出现"
            onClick={close}
          >
            稍后再说
          </button>
        </div>
      </div>
    </>
  );
}
