/**
 * Vitest setup shared by every component test.
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
