// core/dom.js 的辅助类型。
//
// **为什么这一个类型不写在 JSDoc 里**：`Child` 是递归的（数组里可以再放数组，
// `...items.map(...)` 天天产生这种结构），而 JSDoc 的 `@typedef` 不允许类型别名
// 自引用——真正的 TS 语法允许，所以它必须待在 .d.ts 里。其余 DOM 类型都在
// core/dom.js 的 JSDoc 中就近声明。

/** `h()` / `mount()` 接受的子节点。null / undefined / false 被跳过，便于写条件渲染。 */
export type Child = Node | string | number | null | undefined | false | readonly Child[];
