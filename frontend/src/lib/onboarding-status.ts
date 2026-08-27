export interface OnboardingStatus {
  modDone: boolean | null
  commandsDone: boolean | null
  /** null when not applicable (non-affiliate) or when the fetch failed. */
  eventsDone: boolean | null
  timersDone: boolean | null
}

export function countCompleted(status: OnboardingStatus): { completed: number; total: number } {
  const values = Object.values(status).filter((v): v is boolean => v !== null)
  return {
    completed: values.filter(Boolean).length,
    total: values.length,
  }
}
