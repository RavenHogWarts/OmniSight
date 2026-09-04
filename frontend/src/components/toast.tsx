// 操作反馈。写操作（改别名、改分类、改设置）的唯一成功/失败通道。
//
// **保留 `fail('...')` 这种命令式调用**：它的调用点大半在 catch 块里，而那些 catch
// 分布在事件处理器、core/api.ts 的错误映射之后、以及若干 async 流程中间。把它改成
// "往上抛，由某个组件渲染"会让每个调用点多一条状态与一次传递，而它要表达的只是
// "刚才那次写操作失败了"。
//
// 实现是一个极小的外部 store + 一个 React 宿主：命令式 API 不变，渲染归 React。
import { useSyncExternalStore } from 'react';

const LIFETIME_MS = 4200;

export type ToastKind = 'info' | 'ok' | 'error';

interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

let items: readonly ToastItem[] = [];
let nextId = 1;
const listeners = new Set<() => void>();

function publish(next: readonly ToastItem[]): void {
  items = next;
  for (const listener of [...listeners]) listener();
}

export function toast(message: string, kind: ToastKind = 'info'): void {
  const id = nextId++;
  publish([...items, { id, message, kind }]);
  window.setTimeout(() => publish(items.filter((item) => item.id !== id)), LIFETIME_MS);
}

export const ok = (message: string) => toast(message, 'ok');
export const fail = (message: string) => toast(message, 'error');

/** 挂在模板的 `#toasts` 里（它带着 aria-live="polite"）。 */
export function ToastHost() {
  const current = useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => items,
  );
  return (
    <>
      {current.map((item) => (
        <div
          key={item.id}
          className="toast"
          data-kind={item.kind}
          role={item.kind === 'error' ? 'alert' : 'status'}
        >
          <span className="toast__dot" aria-hidden="true" />
          <span>{item.message}</span>
        </div>
      ))}
    </>
  );
}
