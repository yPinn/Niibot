import * as matchers from '@testing-library/jest-dom/matchers'
import { cleanup } from '@testing-library/react'
import { afterEach, expect } from 'vitest'

expect.extend(matchers)

// jsdom ships no ResizeObserver; Radix popper-based components (Tooltip, Select…)
// reference it as soon as they mount. Provide a no-op so those tests don't throw.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// @testing-library/react needs afterEach to be a global to auto-register cleanup.
// With globals: false, we register it manually here.
afterEach(cleanup)
