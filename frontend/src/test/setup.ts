import * as matchers from '@testing-library/jest-dom/matchers'
import { cleanup } from '@testing-library/react'
import { afterEach, expect } from 'vitest'

expect.extend(matchers)

// @testing-library/react needs afterEach to be a global to auto-register cleanup.
// With globals: false, we register it manually here.
afterEach(cleanup)
