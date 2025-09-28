import Section from '@/components/common/Section'
import { useConfigStore } from '@/store/configStore'
import { Stack, TextField } from '@mui/material'
import PriorityStats from './PriorityStats'
import TargetStats from './TargetStats'
import MoodSelector from './MoodSelector'
import StyleSelector from './StyleSelector'
import SkillsPicker from './SkillsPicker'
import RaceScheduler from './RaceScheduler'
import { useEventsData } from '@/hooks/useEventsData'
import EventSetupSection from '../events/EventSetupSection'
import { useEventsSetupStore } from '@/store/eventsSetupStore'
import { useEffect } from 'react'
 
export default function PresetPanel({ compact = false }: { compact?: boolean }) {
  const cfg = useConfigStore((s) => s.config)
  const renamePreset = useConfigStore((s) => s.renamePreset)
  const activeId = cfg.activePresetId ?? cfg.presets[0]?.id
  const active = cfg.presets.find((p) => p.id === activeId)
  const eventsIndex = useEventsData()

  // hydrate Event Setup store from the active preset's saved setup
  const importSetup = useEventsSetupStore((s) => (s as any).importSetup)
  useEffect(() => {
    if (active?.event_setup) {
      importSetup(active.event_setup)
    }
  }, [active?.event_setup, importSetup])

  if (!active) return null

  return (
    <Section title="Preset">
      <Stack spacing={2}>
        <TextField
          label="Preset name"
          size="small"
          value={active.name}
          onChange={(e) => renamePreset(active.id, e.target.value)}
          sx={{ maxWidth: 360 }}
        />
        <PriorityStats presetId={active.id} />
        <TargetStats presetId={active.id} />
        <MoodSelector presetId={active.id} />
        <StyleSelector presetId={active.id} />
        <SkillsPicker presetId={active.id} />
        {eventsIndex && <EventSetupSection index={eventsIndex} />}
        <RaceScheduler presetId={active.id} compact={compact} />
      </Stack>
    </Section>
  )
}
