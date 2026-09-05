// 确认对话框（18 文档 批 5）。
//
// 存在的理由只有两处调用点，而它们都不可撤销：**退出**会停掉采集（用户下次登录前不再
// 记录任何东西），**重新启动**会让本次运行的所有状态从头来。这类动作必须多问一句。
//
// 不用 `window.confirm`：它长得不像这一页，而且它同步阻塞——重启那一路要在确认之后接着
// 弹"正在重启"的浮层，同步对话框会把两者挤在同一帧里。
//
// 形制沿用 `.scrim` + 一张卡（与首启说明同族），焦点进主按钮、Esc 等于取消。
import { useEffect, useRef } from 'react';
import { closeOverlay, openOverlay } from './Drawer.tsx';

export interface ConfirmOptions {
  title: string;
  detail?: string;
  /** 主按钮的文字。默认「确定」。 */
  confirmLabel?: string;
  /** 危险动作：主按钮用错误色。 */
  danger?: boolean;
}

/** @returns 用户点了确认吗 */
export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    const settle = (value: boolean) => {
      closeOverlay();
      resolve(value);
    };
    openOverlay(<ConfirmCard options={options} onSettle={settle} />);
  });
}

function ConfirmCard({
  options,
  onSettle,
}: {
  options: ConfirmOptions;
  onSettle: (value: boolean) => void;
}) {
  const confirm = useRef<HTMLButtonElement | null>(null);
  // 打开它的那个按钮。**在挂载前读**：挂载后 activeElement 已经变了。
  const opener = useRef<HTMLElement | null>(
    typeof document === 'undefined' ? null : (document.activeElement as HTMLElement | null),
  );
  const settle = useRef(onSettle);
  settle.current = onSettle;

  useEffect(() => {
    confirm.current?.focus();
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      settle.current(false);
      opener.current?.focus();
    };
    // 捕获阶段：与抽屉、主题菜单同一套约定（06 文档 §13）。
    document.addEventListener('keydown', onKeydown, true);
    return () => document.removeEventListener('keydown', onKeydown, true);
  }, []);

  const answer = (value: boolean) => {
    onSettle(value);
    opener.current?.focus();
  };

  return (
    <>
      <div className="scrim" onClick={() => answer(false)} />
      <div className="confirm" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
        <h2 id="confirm-title">{options.title}</h2>
        {options.detail ? <p className="muted">{options.detail}</p> : null}
        <div className="confirm__foot">
          <button className="button" type="button" onClick={() => answer(false)}>
            取消
          </button>
          <button
            className={options.danger ? 'button button--danger' : 'button button--primary'}
            type="button"
            ref={confirm}
            onClick={() => answer(true)}
          >
            {options.confirmLabel || '确定'}
          </button>
        </div>
      </div>
    </>
  );
}
