/**
 * Vitest setup shared by every component test.
 *
 * Node 26 defines its own experimental `localStorage` global that returns
 * `undefined` unless `--localstorage-file` is passed, and because vitest's
 * jsdom environment exposes `window` as `globalThis`, that stub shadows the
 * storage jsdom would otherwise provide. Every test touching web storage then
 * fails with "Cannot read properties of undefined". When storage is missing,
 * an in-memory Storage implementing the browser API is installed so those
 * tests run against the semantics they were written for. This is test-only:
 * production code never reads the polyfill.
 *
 * jsdom does not implement `matchMedia`, which framer-motion queries on mount,
 * and it has no ResizeObserver, which recharts requires. Both are stubbed here
 * so component tests exercise real render paths rather than crashing in a
 * polyfill gap.
 *
 * jsdom also has no `URL.createObjectURL`, which the chart preview needs to
 * show a PNG that was fetched through the authenticated API client. The stub
 * hands out a distinct fake URL per call so a test can tell two charts apart,
 * and it is a plain function rather than a mock so the global `restoreAllMocks`
 * cannot strip its implementation between tests.
 */

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!globalThis.URL.createObjectURL) {
  let objectUrlCount = 0;

  globalThis.URL.createObjectURL = () => `blob:preview/${++objectUrlCount}`;

  globalThis.URL.revokeObjectURL = () => {};
}

if (typeof window.localStorage === 'undefined') {
  // Node 26's experimental `localStorage` global shadows jsdom's (see the
  // file header). Hand the tests a real in-memory Storage so getItem starts
  // empty, values round-trip as strings, and clear() empties it -- the
  // browser behaviour the assertions rely on.
  class InMemoryStorage {
    #data = new Map();

    get length() {
      return this.#data.size;
    }

    key(index) {
      return [...this.#data.keys()][index] ?? null;
    }

    getItem(key) {
      return this.#data.has(String(key)) ? this.#data.get(String(key)) : null;
    }

    setItem(key, value) {
      this.#data.set(String(key), String(value));
    }

    removeItem(key) {
      this.#data.delete(String(key));
    }

    clear() {
      this.#data.clear();
    }
  }

  Object.defineProperty(window, 'localStorage', {
    value: new InMemoryStorage(),
    configurable: true,
    writable: true,
  });
}
