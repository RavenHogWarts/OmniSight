// DOM 构造与批量写入。**这一层是整个前端的 XSS 边界**。
//
// `h()` 只接受 `text`，不提供 `html`：应用名与窗口标题来自操作系统，任何进程都能
// 把自己的窗口命名成 `<img src=x onerror=...>`。用 textContent 意味着这类字符串
// 永远只是字符串。tools/check_frontend.py 静态断言全前端没有 innerHTML 赋值。
//
// 类型（07 文档 §2.1）：`h()` 按标签名返回具体的元素类型（`h('canvas')` 就是
// `HTMLCanvasElement`），因此调用方不需要再断言一次。props 的六个特例键各自有类型，
// 其余键按"这个标签真的有这个属性"检查——`h()` 的实现走的就是 `key in node`。

/**
 * `h()` 特殊对待的六个键。其余键直接赋值到元素上，因此按元素自身的属性检查。
 * @typedef {object} SpecialProps
 * @property {string} [class]
 * @property {string | number} [text]
 * @property {Record<string, string | number>} [dataset]
 * @property {Record<string, EventListenerOrEventListenerObject>} [on]
 * @property {Record<string, string | number | boolean | null | undefined>} [attrs]
 * @property {Record<string, string | number>} [style]
 */

/**
 * @template {keyof HTMLElementTagNameMap} K
 * @typedef {SpecialProps & Partial<Omit<HTMLElementTagNameMap[K], 'style' | 'dataset' | 'class'>>} Props
 */

/** @typedef {import('../types/dom.js').Child} Child */

/**
 * 创建元素。props 里的 class/text/dataset/attrs/on 是特例，其余按属性直接赋值。
 * @template {keyof HTMLElementTagNameMap} K
 * @param {K} tag
 * @param {Props<K> | null} [props]
 * @param {...Child} children
 * @returns {HTMLElementTagNameMap[K]}
 */
export function h(tag, props = null, ...children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = /** @type {string} */ (value);
      else if (key === 'text') node.textContent = String(value);
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key === 'on') for (const [type, fn] of Object.entries(value)) node.addEventListener(type, fn);
      else if (key === 'attrs') for (const [name, val] of Object.entries(value)) {
        if (val !== null && val !== undefined && val !== false) node.setAttribute(name, String(val));
      }
      else if (key === 'style') for (const [name, val] of Object.entries(value)) node.style.setProperty(name, String(val));
      else if (key in node) node[key] = value;
      else node.setAttribute(key, String(value));
    }
  }
  append(node, children);
  return node;
}

/**
 * @param {Element | DocumentFragment} parent
 * @param {readonly Child[]} children
 */
function append(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(parent, child);
    else if (typeof child === 'string' || typeof child === 'number') {
      parent.append(document.createTextNode(String(child)));
    } else parent.append(/** @type {Node} */ (child));
  }
}

/**
 * 整块替换容器内容。清空用 replaceChildren 而不是 innerHTML = ''。
 * @template {Element} T
 * @param {T} container
 * @param {...Child} children
 * @returns {T}
 */
export function mount(container, ...children) {
  container.replaceChildren();
  append(container, children);
  return container;
}

/** @param {Element} container */
export function clear(container) {
  container.replaceChildren();
}

/**
 * 只在值真的变了时写 DOM。热点路径（实时计数器）上省掉大量无用的样式重算。
 * @template {Node | null | undefined} T
 * @param {T} node
 * @param {unknown} value
 * @returns {T}
 */
export function setText(node, value) {
  const text = value === null || value === undefined ? '' : String(value);
  if (node && node.textContent !== text) node.textContent = text;
  return node;
}

/**
 * CSS 变量。热力着色、占比条都走这里——JS 不算颜色（06 文档 §11）。
 * @param {HTMLElement | SVGElement | null | undefined} node
 * @param {string} name
 * @param {string | number} value
 */
export function setVar(node, name, value) {
  if (node) node.style.setProperty(name, String(value));
}

// ── 帧合并 ──────────────────────────────────────────────────────────────
// 同一帧内的多次渲染合并成一次，避免布局抖动（07 文档 §6.5）。
/** @type {Map<string, () => void>} */
let queued = new Map();
let frame = 0;

/**
 * @param {string} key
 * @param {() => void} fn
 */
export function schedule(key, fn) {
  queued.set(key, fn);
  if (frame) return;
  frame = requestAnimationFrame(() => {
    const tasks = queued;
    queued = new Map();
    frame = 0;
    for (const task of tasks.values()) {
      try {
        task();
      } catch (error) {
        console.error('渲染任务失败', error);
      }
    }
  });
}

/**
 * keyed 列表更新：以 data-key 复用节点，避免整表重建（07 文档 §6.2）。
 * @template T
 * @param {Element} container
 * @param {readonly T[]} items
 * @param {(item: T) => string | number} keyOf
 * @param {(item: T) => HTMLElement} create
 * @param {((node: HTMLElement, item: T) => void) | null} [update]
 */
export function renderKeyed(container, items, keyOf, create, update) {
  /** @type {Map<string | undefined, HTMLElement>} */
  const existing = new Map();
  for (const node of container.children) {
    const element = /** @type {HTMLElement} */ (node);
    existing.set(element.dataset.key, element);
  }
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const key = String(keyOf(item));
    let node = existing.get(key);
    if (node) existing.delete(key);
    else {
      node = create(item);
      node.dataset.key = key;
    }
    if (update) update(node, item);
    fragment.append(node);
  }
  for (const node of existing.values()) node.remove();
  container.append(fragment);
}

/**
 * 取模板里的挂载点。**找不到就抛**：整块界面消失时，一条明确的报错比
 * `null.append is not a function` 好找。这些 id 的存在由
 * tests/integration/test_frontend_contract.py 对着 dashboard.html 断言。
 * @param {string} id
 * @returns {HTMLElement}
 */
export function mountPoint(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error(`挂载点 #${id} 不在模板里`);
  return node;
}

/**
 * 容器内当前可见的可聚焦元素。焦点陷阱（抽屉、首次运行对话框）用它。
 * `querySelectorAll` 给的是 `NodeListOf<Element>`，而 `Element` 上既没有 `focus`
 * 也没有 `offsetParent`——两处焦点陷阱各断言一次不如收在这里。
 * @param {Element} root
 * @param {string} selector
 * @returns {HTMLElement[]}
 */
export function focusables(root, selector) {
  const nodes = /** @type {NodeListOf<HTMLElement>} */ (root.querySelectorAll(selector));
  return [...nodes].filter((node) => node.offsetParent !== null);
}

/**
 * 事件目标向上找最近的匹配元素。`event.target` 的静态类型是 `EventTarget`（既没有
 * `closest` 也可能是 null），每个调用点各断言一次不如收在这里——顺带补上原先缺的
 * null 分支：target 为 null 时原写法会抛。
 * @param {Event} event
 * @param {string} selector
 * @returns {HTMLElement | null}
 */
export function closestFrom(event, selector) {
  const target = /** @type {Element | null} */ (event.target);
  return /** @type {HTMLElement | null} */ (target?.closest(selector) ?? null);
}

/**
 * 事件委托。返回注销函数，视图卸载时调用。
 * @param {Element} root
 * @param {string} type
 * @param {string} selector
 * @param {(event: Event, target: HTMLElement) => void} handler
 * @returns {() => void}
 */
export function delegate(root, type, selector, handler) {
  /** @param {Event} event */
  const listener = (event) => {
    const target = /** @type {Element | null} */ (event.target)?.closest(selector);
    if (target && root.contains(target)) handler(event, /** @type {HTMLElement} */ (target));
  };
  root.addEventListener(type, listener);
  return () => root.removeEventListener(type, listener);
}

/**
 * @param {EventTarget} node
 * @param {string} type
 * @param {EventListenerOrEventListenerObject} handler
 * @param {boolean | AddEventListenerOptions} [options]
 * @returns {() => void}
 */
export function on(node, type, handler, options) {
  node.addEventListener(type, handler, options);
  return () => node.removeEventListener(type, handler, options);
}
