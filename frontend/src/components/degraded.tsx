// 降级表达的第一级：全局横幅（06 文档 §4.2）。
//
// 三条规则在这里体现两条：
//   - 文案三段全部来自后端 degraded[]（title/detail/hint），前端不编。
//   - 关闭状态记在 localStorage，**能力恢复后重新出现**：记的是那一条的 code，
//     而不是"用户关过横幅"这一个布尔值。否则用户关掉键盘降级提示之后，
//     下次换成完全不同的一条降级也不会显示。
//
// severity == error 才上横幅。warning 一级留给面板内说明块与图表斜纹，
// 全都做成横幅会让首期 Windows 上的用户被三条黄条挡住半个屏幕。
import { useState } from 'react';
import { useSlice } from '../core/useStore.ts';
import { Icon } from './Icon.tsx';
import type { Capabilities, DegradedNotice } from '../types/api.d.ts';

const DISMISS_KEY = 'omnisight.dismissed';

function dismissed(): Set<string> {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    return new Set<string>(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

function remember(code: string): Set<string> {
  const codes = dismissed();
  codes.add(code);
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify([...codes]));
  } catch {
    // 关不掉就下次还显示，比崩掉好。
  }
  return codes;
}

/** 挂在模板的 `#banners` 里（它带着 aria-live="polite"）。 */
export function Banners() {
  const degraded = useSlice('degraded');
  // 本地副本只为触发重渲染；真值在 localStorage 里（跨会话保留）。
  const [hidden, setHidden] = useState(dismissed);
  const shown = (degraded || []).filter(
    (notice) => notice.severity === 'error' && !hidden.has(notice.code || notice.title),
  );
  if (!shown.length) return null;
  return (
    <>
      {shown.map((notice) => (
        <Banner
          key={notice.code || notice.title}
          notice={notice}
          onClose={() => setHidden(remember(notice.code || notice.title))}
        />
      ))}
    </>
  );
}

function Banner({ notice, onClose }: { notice: DegradedNotice; onClose: () => void }) {
  return (
    <div className="banner" data-severity={notice.severity || 'warning'} role="alert">
      <span className="banner__mark" aria-hidden="true">
        <Icon name="warning" />
      </span>
      <div className="banner__body">
        <div className="banner__title">{notice.title || '能力受限'}</div>
        {notice.detail ? <div className="banner__detail">{notice.detail}</div> : null}
        {notice.hint ? <div className="banner__hint">{notice.hint}</div> : null}
      </div>
      <button className="banner__close" type="button" aria-label="关闭提示" onClick={onClose}>
        <Icon name="close" />
      </button>
    </div>
  );
}

/** 面板问"我依赖的能力在不在"。**只读布尔值，不读 platform.id**（07 文档 §10）。 */
export function capabilityOf(capabilities: Capabilities | null | undefined, name: string): boolean {
  if (!capabilities) return true; // 尚未探明：先按可用渲染，status 到位后再降级
  return (capabilities as unknown as Record<string, unknown>)[name] !== false;
}

/**
 * 找出与某个能力相关的那条 degraded 说明，好把后端文案原样显示在面板里。
 *
 * 只按 `code` 匹配。原先还有一个 `notice.capability === capability` 分支，而
 * `DegradedNotice` 上**没有** `capability` 字段（types/api.d.ts，由契约测试对着真实
 * 响应核对）——那个分支永远是 undefined 比较，从来没命中过。
 */
export function noticeFor(
  degraded: readonly DegradedNotice[] | null | undefined,
  capability: string,
): DegradedNotice | null {
  return (degraded || []).find((notice) => notice.code === capability) || null;
}
