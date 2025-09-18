export type DateKey = string // Y{year}-{MM}-{half}

export function monthHalfFromDay(day: number): 1 | 2 {
  return day <= 1 ? 1 : 2
}

export function toDateKey(year: number, month: number, day: number): DateKey {
  const half = monthHalfFromDay(day)
  const mm = String(month).padStart(2, '0')
  return `Y${year}-${mm}-${half}`
}
