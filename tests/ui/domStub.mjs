class TestElement {}

class ClassList {
  constructor() {
    this.values = new Set();
  }

  add(...tokens) {
    tokens.forEach((token) => this.values.add(token));
  }

  remove(...tokens) {
    tokens.forEach((token) => this.values.delete(token));
  }

  toggle(token, force) {
    if (force === undefined) {
      if (this.values.has(token)) {
        this.values.delete(token);
        return false;
      }
      this.values.add(token);
      return true;
    }
    if (force) {
      this.values.add(token);
      return true;
    }
    this.values.delete(token);
    return false;
  }

  contains(token) {
    return this.values.has(token);
  }
}

export class MockElement extends TestElement {
  constructor(id = "") {
    super();
    this.id = id;
    this.innerHTML = "";
    this.textContent = "";
    this.classList = new ClassList();
    this.attributes = new Map();
    this.dataset = {};
    this.style = {};
    this.children = [];
    this.offsetWidth = 320;
    this.offsetHeight = 180;
    this.rect = { left: 100, top: 120, width: 20, height: 20 };
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  getBoundingClientRect() {
    return this.rect;
  }

  closest(selector) {
    if (selector.startsWith(".") && this.classList.contains(selector.slice(1))) {
      return this;
    }
    return null;
  }

  contains(target) {
    return target === this || this.children.includes(target);
  }
}

export function installDom() {
  globalThis.Element = TestElement;

  let now = 0;
  let timerId = 0;
  const elements = new Map();
  const listeners = new Map();
  const storage = new Map();

  const documentElement = new MockElement("html");

  const document = {
    documentElement,
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, new MockElement(id));
      }
      return elements.get(id);
    },
    querySelector(selector) {
      if (selector === ".settings-wrap") {
        return elements.get("settingsWrap") ?? null;
      }
      return null;
    },
    addEventListener(type, handler) {
      const handlers = listeners.get(type) ?? [];
      handlers.push(handler);
      listeners.set(type, handlers);
    },
    dispatchEvent(type, event) {
      for (const handler of listeners.get(type) ?? []) {
        handler(event);
      }
    },
  };

  globalThis.document = document;
  globalThis.window = {
    innerWidth: 1024,
    innerHeight: 768,
    setTimeout(callback, delay) {
      timerId += 1;
      return { id: timerId, callback, delay };
    },
    clearTimeout() {},
    setInterval(callback, delay) {
      timerId += 1;
      return { id: timerId, callback, delay };
    },
    clearInterval() {},
  };
  globalThis.performance = {
    now: () => now,
  };
  globalThis.localStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, String(value));
    },
    clear() {
      storage.clear();
    },
  };

  return {
    document,
    element: (id) => document.getElementById(id),
    createElement: (id = "") => new MockElement(id),
    reset() {
      elements.clear();
      storage.clear();
      documentElement.innerHTML = "";
      documentElement.textContent = "";
      documentElement.classList = new ClassList();
      documentElement.attributes = new Map();
      documentElement.style = {};
      now = 0;
    },
    setNow(value) {
      now = Number(value) || 0;
    },
  };
}
