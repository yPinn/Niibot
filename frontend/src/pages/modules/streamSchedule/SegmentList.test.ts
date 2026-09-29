import { describe, expect, it } from 'vitest'

import { timeSlotOptions } from './segmentTimeSlots'

describe('timeSlotOptions', () => {
  it('offers quarter-hour internal segment boundaries without including the end time', () => {
    expect(timeSlotOptions('20:00', 60).map(option => option.value)).toEqual([
      '20:00',
      '20:15',
      '20:30',
      '20:45',
    ])
  })

  it('keeps quarter-hour boundaries across midnight', () => {
    expect(timeSlotOptions('23:45', 45).map(option => option.value)).toEqual([
      '23:45',
      '00:00',
      '00:15',
    ])
  })
})
