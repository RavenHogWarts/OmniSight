// DOM 构造与批量写入。**这一层是整个前端的 XSS 边界**。
//
// `h()` 只接受 `text`，不提供 `html`：应用名与窗口标题来自操作系统，任何进程都能
// 把自己的窗口命名成 `<img src=x onerror=...>`。用 textContent 意味着这类字符串
// 永远只是字符串。tools/check_frontend.py 静态断言全前端没有 innerHTML 赋值。

/** 创建元素。props 里的 class/text/dataset/attrs/on 是特例，其余按属性直接赋值。 */
export function h(tag, props = null, ...children) {
  const node = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.className = value;
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

function append(parent, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(parent, child);
    else if (typeof child === 'string' || typeof child === 'number') {
      parent.append(document.createTextNode(String(child)));
    } else parent.append(child);
  }
}

/** 整块替换容器内容。清空用 replaceChildren 而不是 innerHTML = ''。 */
export function mount(container, ...children) {
  container.replaceChildren();
  append(container, children);
  return container;
}

export function clear(container) {
  container.replaceChildren();
}

/** 只在值真的变了时写 DOM。热点路径（实时计数器）上省掉大量无用的样式重算。 */
export function setText(node, value) {
  const text = value === null || value === undefined ? '' : String(value);
  if (node && node.textContent !== text) node.textContent = text;
  return node;
}

/** CSS 变量。热力着色、占比条都走这里——JS 不算颜色（06 文档 §11）。 */
export function setVar(node, name, value) {
  if (node) node.style.setProperty(name, String(value));
}

// ── 帧合并 ──────────────────────────────────────────────────────────────
// 同一帧内的多次渲染合并成一次，避免布局抖动（07 文档 §6.5）。
let queued = new Map();
let frame = 0;

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

/** keyed 列表更新：以 data-key 复用节点，避免整表重建（07 文档 §6.2）。 */
export function renderKeyed(container, items, keyOf, create, update) {
  const existing = new Map();
  for (const node of container.children) existing.set(node.dataset.key, node);
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

/** 事件委托。返回注销函数，视图卸载时调用。 */
export function delegate(root, type, selector, handler) {
  const listener = (event) => {
    const target = event.target.closest(selector);
    if (target && root.contains(target)) handler(event, target);
  };
  root.addEventListener(type, listener);
  return () => root.removeEventListener(type, listener);
}

export function on(node, type, handler, options) {
  node.addEventListener(type, handler, options);
  return () => node.removeEventListener(type, handler, options);
}
