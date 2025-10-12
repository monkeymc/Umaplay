import Section from '@/components/common/Section'
import { useConfigStore } from '@/store/configStore'
import { Stack, TextField, FormControlLabel, Switch, IconButton, Tooltip, Typography } from '@mui/material'
import { Info as InfoIcon } from '@mui/icons-material'
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
        <Section title="Bot Strategy / Policy">
          <Stack spacing={1}>

            <FormControlLabel
              control={
                <Switch
                  checked={!!active.raceIfNoGoodValue}
                  onChange={(e) => patchPreset(active.id!, 'raceIfNoGoodValue', e.target.checked)}
                />
              }
              label={
                <Stack direction="row" alignItems="center" spacing={0.5}>
                  <Typography variant="body1">Allow Racing over low training</Typography>
                  <Tooltip title="If for example our best option is SV <= 1 (e.g. 1 rainbow, 1 friend training, etc). If this option is enabled, bot will prefer to look for race (hopefully G2 or G1) to farm skill pts and stats.">
                    <IconButton size="small" color="info">
                      <InfoIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              }
            />
            <FormControlLabel
              control={
                <Switch
                  checked={!!active.prioritizeHint}
                  onChange={(e) => patchPreset(active.id!, 'prioritizeHint', e.target.checked)}
                />
              }
              label={
                <Stack direction="row" alignItems="center" spacing={0.5}>
                  <Typography variant="body1">Prioritize hint tiles</Typography>
                  <Tooltip title="Give priority to hint tiles during training, value of hint is increased from 0.75 to 2.25. Nevertheless, If for some reason you have hint in guts and the best SV is 3.5 (triple rainbow) in another tile -> Even if hint priority is enabled, bot will prefer that amazing SV.">
                    <IconButton size="small" color="info">
                      <InfoIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              }
            />
          </Stack>
        </Section>
        {eventsIndex && <EventSetupSection index={eventsIndex} />}
        <RaceScheduler presetId={active.id} compact={compact} />
      </Stack>
    </Section>
  )
}