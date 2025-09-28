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
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const activeId = cfg.activePresetId ?? cfg.presets[0]?.id
  const active = cfg.presets.find((p) => p.id === activeId)
  const eventsIndex = useEventsData()

  // 1) Hydrate Event Setup only when active preset id changes
  const importSetup = useEventsSetupStore((s) => s.importSetup)
  const revision = useEventsSetupStore((s) => s.revision)
  useEffect(() => {
    if (active?.event_setup) importSetup(active.event_setup)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId])

  // 2) On any EventSetup change, write it back into the active preset (so export & LocalStorage keep it)
  useEffect(() => {
    if (!activeId) return
    const setup = useEventsSetupStore.getState().getSetup()
    patchPreset(activeId, 'event_setup', setup)
  }, [activeId, revision, patchPreset])

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