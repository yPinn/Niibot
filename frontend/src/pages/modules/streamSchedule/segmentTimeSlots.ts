import { endTimeFor } from './time'

const STEP_MINUTES = 15

/** Quarter-hour clock values inside a schedule window, including midnight wrap. */
export function timeSlotOptions(
  startTime: string,
  durationMinutes: number
): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = []
  for (let offset = 0; offset < durationMinutes; offset += STEP_MINUTES) {
    const time = endTimeFor(startTime, offset)
    options.push({ value: time, label: offset === 0 ? `${time}（開台）` : time })
  }
  return options
}
