class TestClassList {
  constructor() {
    this.values = new Set();
  }

  add(...names) {
    names.forEach(name => this.values.add(name));
  }

  remove(...names) {
    names.forEach(name => this.values.delete(name));
  }

  toggle(name, force) {
    if (force === undefined) {
      if (this.values.has(name)) this.values.delete(name);
      else this.values.add(name);
    } else if (force) this.values.add(name);
    else this.values.delete(name);
    return this.values.has(name);
  }

  contains(name) {
    return this.values.has(name);
  }
}

class TestStyle {
  constructor() {
    this.values = new Map();
  }

  setProperty(name, value) {
    this.values.set(name, String(value));
    this[name] = String(value);
  }

  getPropertyValue(name) {
    return this.values.get(name) || "";
  }
}

export class TestElement {
  constructor(id = "") {
    this.id = id;
    this.reset();
  }

  reset() {
    this.innerHTML = "";
    this.textContent = "";
    this.classList = new TestClassList();
    this.style = new TestStyle();
    this.dataset = {};
    this.attributes = new Map();
    this.disabled = false;
    this.scrollTop = 0;
    this.offsetWidth = 0;
    this.offsetHeight = 0;
    this.listeners = new Map();
    this.queries = new Map();
    this.parentElement = null;
    this.focused = false;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(type, callback) {
    const callbacks = this.listeners.get(type) || [];
    callbacks.push(callback);
    this.listeners.set(type, callbacks);
  }

  setQuery(selector, ...elements) {
    this.queries.set(selector, elements.flat());
  }

  querySelector(selector) {
    return (this.queries.get(selector) || [])[0] || null;
  }

  querySelectorAll(selector) {
    return [...(this.queries.get(selector) || [])];
  }

  matches(selector) {
    if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    if (selector === "[data-chart-tooltip-close]") {
      return Object.hasOwn(this.dataset, "chartTooltipClose");
    }
    return false;
  }

  closest(selector) {
    if (this.matches(selector)) return this;
    return this.parentElement?.closest(selector) || null;
  }

  contains(other) {
    if (other === this) return true;
    return [...this.queries.values()].flat().some(child => child === other || child.contains?.(other));
  }

  replaceChildren() {
    this.innerHTML = "";
    this.textContent = "";
  }

  getBoundingClientRect() {
    return { left: 0, top: 0, width: this.offsetWidth, height: this.offsetHeight };
  }

  focus() {
    this.focused = true;
  }

  scrollIntoView() {}
}

export function installDom() {
  const elements = new Map();
  const documentListeners = new Map();
  const storage = new Map();
  const intervals = new Map();
  let now = 0;
  let timerId = 0;

  const element = (id) => {
    if (!elements.has(id)) elements.set(id, new TestElement(id));
    return elements.get(id);
  };

  const documentElement = new TestElement("documentElement");
  documentElement.clientWidth = 1024;
  documentElement.clientHeight = 768;

  const document = {
    documentElement,
    getElementById: id => element(id),
    createElement: tag => new TestElement(tag),
    querySelector(selector) {
      if (selector.startsWith("#")) return elements.get(selector.slice(1)) || null;
      return [...elements.values()].find(candidate => candidate.matches(selector)) || null;
    },
    querySelectorAll(selector) {
      return [...elements.values()].filter(candidate => candidate.matches(selector));
    },
    addEventListener(type, callback) {
      const callbacks = documentListeners.get(type) || [];
      callbacks.push(callback);
      documentListeners.set(type, callbacks);
    },
  };

  const localStorage = {
    getItem: key => storage.has(key) ? storage.get(key) : null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
    clear: () => storage.clear(),
  };

  const window = {
    innerWidth: 1024,
    innerHeight: 768,
    setInterval(callback) {
      timerId += 1;
      intervals.set(timerId, callback);
      return timerId;
    },
    clearInterval(id) {
      intervals.delete(id);
    },
    setTimeout(callback) {
      callback();
      timerId += 1;
      return timerId;
    },
    requestAnimationFrame(callback) {
      callback(now + 2_000);
      timerId += 1;
      return timerId;
    },
  };

  globalThis.Element = TestElement;
  globalThis.document = document;
  globalThis.window = window;
  globalThis.localStorage = localStorage;
  globalThis.performance = { now: () => now };
  globalThis.requestAnimationFrame = window.requestAnimationFrame;

  return {
    document,
    element,
    createElement: id => new TestElement(id),
    setNow(value) {
      now = Number(value);
    },
    runInterval(id) {
      const callback = intervals.get(id);
      if (callback) callback();
    },
    dispatchDocument(type, event) {
      for (const callback of documentListeners.get(type) || []) callback(event);
    },
    reset() {
      for (const candidate of elements.values()) candidate.reset();
      documentElement.reset();
      documentElement.clientWidth = 1024;
      documentElement.clientHeight = 768;
      storage.clear();
      intervals.clear();
      now = 0;
    },
  };
}
