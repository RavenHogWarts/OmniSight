// 极小 DOM 垫片。**它不是浏览器**——只实现 h() / renderKeyed / buildKeyboard 真正用到的
// 那几个 API，用来对渲染结果做结构断言（节点数、属性值、CSS 变量）。
//
// 为什么值得有：键盘渲染器是 M3 收益最大的一处改造（旧版 860 行硬编码 DOM），而它的
// 正确性表现为"每一行的键宽倍数加起来对得上"这种结构性质，恰好可以在没有浏览器的
// 情况下验证。视觉层面的东西（颜色、字号、是否溢出）这里测不了，那部分靠人工验收。
//
// 垫片与真实 DOM 的差异只在于：没有布局、没有事件冒泡的完整语义、querySelector 只支持
// 单个类选择器。断言时不要依赖这三样。

class ClassList {
  constructor(node) {
    this.node = node;
    this.items = new Set();
  }

  add(...names) {
    for (const name of names) this.items.add(name);
  }

  remove(...names) {
    for (const name of names) this.items.delete(name);
  }

  contains(name) {
    return this.items.has(name);
  }

  toString() {
    return [...this.items].join(' ');
  }
}

class Style {
  constructor() {
    this.props = new Map();
  }

  setProperty(name, value) {
    this.props.set(name, String(value));
  }

  getPropertyValue(name) {
    return this.props.get(name) ?? '';
  }
}

class Node {
  constructor(tag) {
    this.tagName = String(tag || '').toUpperCase();
    this.children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.style = new Style();
    this.classList = new ClassList(this);
    this.listeners = new Map();
    this.parentElement = null;
    this._text = '';
    this.hidden = false;
    this.disabled = false;
  }

  get className() {
    return this.attributes.get('class') || '';
  }

  set className(value) {
    this.attributes.set('class', String(value));
    this.classList.items = new Set(String(value).split(/\s+/).filter(Boolean));
  }

  get textContent() {
    if (this.children.length) return this.children.map((child) => child.textContent).join('');
    return this._text;
  }

  set textContent(value) {
    this.children = [];
    this._text = String(value);
  }

  setAttribute(name, value) {
    if (name === 'class') {
      this.className = value;
      return;
    }
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    if (name === 'class') return this.className;
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  append(...nodes) {
    for (const node of nodes) {
      if (node === null || node === undefined) continue;
      if (node instanceof Fragment) {
        this.append(...node.children.splice(0));
        continue;
      }
      if (node.parentElement) node.parentElement.children = node.parentElement.children.filter((item) => item !== node);
      node.parentElement = this;
      this.children.push(node);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentElement = null;
    this.children = [];
    this._text = '';
    this.append(...nodes);
  }

  replaceWith(node) {
    if (!this.parentElement) return;
    const index = this.parentElement.children.indexOf(this);
    if (index >= 0) {
      this.parentElement.children[index] = node;
      node.parentElement = this.parentElement;
      this.parentElement = null;
    }
  }

  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
    this.parentElement = null;
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(handler);
  }

  removeEventListener(type, handler) {
    this.listeners.get(type)?.delete(handler);
  }

  contains(node) {
    if (node === this) return true;
    return this.children.some((child) => child.contains(node));
  }

  /** 只支持单个类选择器与标签名，够用即止。 */
  querySelector(selector) {
    return this.queryAll(selector)[0] ?? null;
  }

  querySelectorAll(selector) {
    return this.queryAll(selector);
  }

  queryAll(selector) {
    const found = [];
    const matches = (node) =>
      selector.startsWith('.')
        ? node.classList.contains(selector.slice(1))
        : node.tagName === selector.toUpperCase();
    const walk = (node) => {
      for (const child of node.children) {
        if (matches(child)) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }

  closest(selector) {
    let node = this;
    while (node) {
      const matches = selector.startsWith('.')
        ? node.classList.contains(selector.slice(1))
        : node.tagName === selector.toUpperCase();
      if (matches) return node;
      node = node.parentElement;
    }
    return null;
  }

  getBoundingClientRect() {
    return { width: 600, height: 200, left: 0, top: 0 };
  }

  focus() {
    globalThis.document.activeElement = this;
  }
}

class Fragment extends Node {
  constructor() {
    super('#fragment');
  }
}

class TextNode extends Node {
  constructor(text) {
    super('#text');
    this._text = String(text);
  }
}

/** 装上垫片。返回卸载函数，测试之间不留状态。 */
export function installDom() {
  const document = {
    createElement: (tag) => new Node(tag),
    createTextNode: (text) => new TextNode(text),
    createDocumentFragment: () => new Fragment(),
    documentElement: new Node('html'),
    body: new Node('body'),
    activeElement: null,
    addEventListener() {},
    removeEventListener() {},
    getElementById: () => null,
  };
  globalThis.document = document;
  globalThis.Node = Node;
  globalThis.getComputedStyle = () => ({ getPropertyValue: () => '' });
  globalThis.requestAnimationFrame = (fn) => {
    fn();
    return 1;
  };
  globalThis.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
  globalThis.window = {
    devicePixelRatio: 1,
    innerWidth: 1440,
    innerHeight: 900,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    setTimeout: () => 0,
    clearTimeout() {},
    setInterval: () => 0,
    clearInterval() {},
  };
  globalThis.CustomEvent = class {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail;
    }
  };
  return () => {
    delete globalThis.document;
    delete globalThis.window;
    delete globalThis.getComputedStyle;
    delete globalThis.requestAnimationFrame;
    delete globalThis.ResizeObserver;
  };
}
