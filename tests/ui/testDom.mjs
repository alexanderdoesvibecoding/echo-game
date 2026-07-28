/** Minimal deterministic DOM implementation used by Node-based UI tests. */

/** Implement the classList subset exercised by the UI. */
class TestClassList {
  /** Initialize an empty class-name set. */
  constructor() {
    this.values = new Set();
  }

  /** Add one or more class names. */
  add(...names) {
    names.forEach(name => this.values.add(name));
  }

  /** Remove one or more class names. */
  remove(...names) {
    names.forEach(name => this.values.delete(name));
  }

  /** Toggle a class with optional explicit force semantics. */
  toggle(name, force) {
    if (force === undefined) {
      if (this.values.has(name)) this.values.delete(name);
      else this.values.add(name);
    } else if (force) this.values.add(name);
    else this.values.delete(name);
    return this.values.has(name);
  }

  /** Report whether a class name is present. */
  contains(name) {
    return this.values.has(name);
  }
}

/** Implement the CSSStyleDeclaration subset exercised by the UI. */
class TestStyle {
  /** Initialize an empty CSS property map. */
  constructor() {
    this.values = new Map();
  }

  /** Store one CSS custom property. */
  setProperty(name, value) {
    this.values.set(name, String(value));
    this[name] = String(value);
  }

  /** Return a stored CSS custom property or an empty string. */
  getPropertyValue(name) {
    return this.values.get(name) || "";
  }
}

/** Implement the DOM element subset required by UI tests. */
export class TestElement {
  /** Initialize one deterministic test element. */
  constructor(id = "") {
    this.id = id;
    this.reset();
  }

  /** Restore mutable element state between tests. */
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

  /** Store one string-valued DOM attribute. */
  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  /** Return a stored DOM attribute or null. */
  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  /** Register an event callback by type. */
  addEventListener(type, callback) {
    const callbacks = this.listeners.get(type) || [];
    callbacks.push(callback);
    this.listeners.set(type, callbacks);
  }

  /** Preconfigure selector results returned by this element. */
  setQuery(selector, ...elements) {
    this.queries.set(selector, elements.flat());
  }

  /** Return the first preconfigured selector result. */
  querySelector(selector) {
    return (this.queries.get(selector) || [])[0] || null;
  }

  /** Return every preconfigured selector result. */
  querySelectorAll(selector) {
    return [...(this.queries.get(selector) || [])];
  }

  /** Match simple selectors used by the application. */
  matches(selector) {
    if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
    if (selector.startsWith("#")) return this.id === selector.slice(1);
    if (selector === "[data-chart-tooltip-close]") {
      return Object.hasOwn(this.dataset, "chartTooltipClose");
    }
    return false;
  }

  /** Walk ancestors until a matching element is found. */
  closest(selector) {
    if (this.matches(selector)) return this;
    return this.parentElement?.closest(selector) || null;
  }

  /** Report whether another element is this node or a descendant. */
  contains(other) {
    if (other === this) return true;
    return [...this.queries.values()].flat().some(child => child === other || child.contains?.(other));
  }

  /** Clear the element's rendered HTML. */
  replaceChildren() {
    this.innerHTML = "";
    this.textContent = "";
  }

  /** Return the configured deterministic layout rectangle. */
  getBoundingClientRect() {
    return { left: 0, top: 0, width: this.offsetWidth, height: this.offsetHeight };
  }

  /** Mark this element as the document's active element. */
  focus() {
    this.focused = true;
  }

  /** Provide the no-op scrolling hook expected by tutorial code. */
  scrollIntoView() {}
}

/** Install deterministic window, document, storage, and element test doubles. */
export function installDom() {
  const elements = new Map();
  const documentListeners = new Map();
  const storage = new Map();
  const intervals = new Map();
  let now = 0;
  let timerId = 0;

  /** Intern test elements so repeated ID lookups preserve browser-like identity. */
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
    /** Resolve the simple ID and class selectors used by application tests. */
    querySelector(selector) {
      if (selector.startsWith("#")) return elements.get(selector.slice(1)) || null;
      return [...elements.values()].find(candidate => candidate.matches(selector)) || null;
    },
    /** Return every interned element matching a supported selector. */
    querySelectorAll(selector) {
      return [...elements.values()].filter(candidate => candidate.matches(selector));
    },
    /** Register a document-level delegated event listener. */
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
    /** Register an interval callback without starting real wall-clock work. */
    setInterval(callback) {
      timerId += 1;
      intervals.set(timerId, callback);
      return timerId;
    },
    /** Remove a registered deterministic interval. */
    clearInterval(id) {
      intervals.delete(id);
    },
    /** Execute timer callbacks immediately while returning a unique timer ID. */
    setTimeout(callback) {
      callback();
      timerId += 1;
      return timerId;
    },
    /** Execute animation frames at a deterministic future timestamp. */
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
    /** Set the high-resolution clock value observed by application code. */
    setNow(value) {
      now = Number(value);
    },
    /** Manually execute one registered interval tick. */
    runInterval(id) {
      const callback = intervals.get(id);
      if (callback) callback();
    },
    /** Dispatch an event through registered document-level listeners. */
    dispatchDocument(type, event) {
      for (const callback of documentListeners.get(type) || []) callback(event);
    },
    /** Restore all DOM, storage, timer, and clock state between tests. */
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
