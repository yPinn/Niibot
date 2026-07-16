import { describe, expect, it } from 'vitest'

import { countCompleted, type OnboardingStatus } from '@/lib/onboarding-status'

describe('countCompleted', () => {
  it('counts every item done', () => {
    const status: OnboardingStatus = {
      modDone: true,
      commandsDone: true,
      eventsDone: true,
      timersDone: true,
    }
    expect(countCompleted(status)).toEqual({ completed: 4, total: 4 })
  })

  it('counts nothing done', () => {
    const status: OnboardingStatus = {
      modDone: false,
      commandsDone: false,
      eventsDone: false,
      timersDone: false,
    }
    expect(countCompleted(status)).toEqual({ completed: 0, total: 4 })
  })

  it('counts a mixed state', () => {
    const status: OnboardingStatus = {
      modDone: true,
      commandsDone: false,
      eventsDone: true,
      timersDone: false,
    }
    expect(countCompleted(status)).toEqual({ completed: 2, total: 4 })
  })

  it('excludes null (not-applicable) items from both completed and total', () => {
    const status: OnboardingStatus = {
      modDone: true,
      commandsDone: true,
      eventsDone: null, // e.g. non-affiliate
      timersDone: false,
    }
    expect(countCompleted(status)).toEqual({ completed: 2, total: 3 })
  })

  it('excludes null items caused by a fetch failure the same way as not-applicable', () => {
    const status: OnboardingStatus = {
      modDone: null,
      commandsDone: true,
      eventsDone: true,
      timersDone: true,
    }
    expect(countCompleted(status)).toEqual({ completed: 3, total: 3 })
  })

  it('returns 0/0 when every item is null', () => {
    const status: OnboardingStatus = {
      modDone: null,
      commandsDone: null,
      eventsDone: null,
      timersDone: null,
    }
    expect(countCompleted(status)).toEqual({ completed: 0, total: 0 })
  })
})
