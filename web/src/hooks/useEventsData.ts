import { useEffect, useState } from 'react'
import type { EventsIndex } from '@/types/events'
import { loadEventsIndex } from '@/utils/eventsIndex'

export function useEventsData() {
  const [index, setIndex] = useState<EventsIndex | null>(null)
  useEffect(() => { (async () => setIndex(await loadEventsIndex()))() }, [])
  return index
}
