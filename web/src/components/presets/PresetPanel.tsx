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
import { useEffect, useMemo, useRef } from 'react'
import FieldRow from '@/components/common/FieldRow'
import type { Preset, ScenarioConfig } from '@/models/types'

const normalizeScenario = (value?: string | null): 'ura' | 'unity_cup' =>
  value === 'unity_cup' ? 'unity_cup' : 'ura'

export default function PresetPanel({ compact = false }: { compact?: boolean }) {
  const uiScenarioKey = useConfigStore((s) => s.uiScenarioKey)
  const uiSelectedPresetId = useConfigStore((s) => s.uiSelectedPresetId)
  const generalActiveScenario = useConfigStore((s) => s.config.general?.activeScenario)
  const scenarios = useConfigStore((s) => s.config.scenarios)

  const scenarioKey = normalizeScenario(uiScenarioKey ?? generalActiveScenario)
  const branch = useMemo(() => {
    const map = (scenarios ?? {}) as Record<string, ScenarioConfig>
    const raw = map[scenarioKey] ?? { presets: [], activePresetId: undefined }
    const presets: Preset[] = Array.isArray(raw.presets) ? (raw.presets as Preset[]) : []
    const activePresetId = raw.activePresetId && presets.some((p) => p.id === raw.activePresetId)
      ? raw.activePresetId
      : presets[0]?.id
    return { presets, activePresetId }
  }, [scenarios, scenarioKey])

  const presets = branch.presets
  const selectedId = useMemo(() => {
    if (uiSelectedPresetId && presets.some((p) => p.id === uiSelectedPresetId)) {
      return uiSelectedPresetId
    }
    return branch.activePresetId ?? presets[0]?.id
  }, [uiSelectedPresetId, branch.activePresetId, presets])

  const selected = useMemo(() => (selectedId ? presets.find((p) => p.id === selectedId) : undefined), [presets, selectedId])
  const renamePreset = useConfigStore((s) => s.renamePreset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const eventsIndex = useEventsData()
  const lastSyncedRevision = useRef<number>(-1)

  // 1) Hydrate Event Setup only when active preset id changes
  const importSetup = useEventsSetupStore((s) => s.importSetup)
  const revision = useEventsSetupStore((s) => s.revision)
  useEffect(() => {
    // Defer hydration to next tick to avoid blocking tab switch
    const timer = setTimeout(() => {
      if (selected?.event_setup) importSetup(selected.event_setup)
      lastSyncedRevision.current = revision
    }, 0)
    return () => clearTimeout(timer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId])

  // 2) On any EventSetup change, write it back into the active preset (so export & LocalStorage keep it)
  useEffect(() => {
    if (!selectedId || lastSyncedRevision.current === revision) return
    lastSyncedRevision.current = revision
    const setup = useEventsSetupStore.getState().getSetup()
    patchPreset(selectedId, 'event_setup', setup)
  }, [revision, selectedId, patchPreset])

  if (!selected) return null

  return (
    <Section title="Preset" sx={{ width: '100%', maxWidth: 'none' }}>
      <Stack spacing={2} sx={{ width: '100%' }}>
        <TextField
          label="Preset name"
          size="small"
          value={selected.name}
          onChange={(e) => renamePreset(selected.id, e.target.value)}
          sx={{ maxWidth: 360 }}
        />
        <PriorityStats presetId={selected.id} />
        <TargetStats presetId={selected.id} />
        <MoodSelector presetId={selected.id} />
        <StyleSelector presetId={selected.id} />
        <FieldRow
          label="Skill points threshold"
          info="Open the Skills screen on race days once points are at or above this value."
          control={
            <TextField
              size="small"
              type="number"
              value={selected.skillPtsCheck ?? 600}
              onChange={(e) =>
                patchPreset(
                  selected.id!,
                  'skillPtsCheck',
                  Math.max(0, Number.isFinite(Number(e.target.value)) ? Number(e.target.value) : 0),
                )
              }
              inputProps={{ min: 0 }}
              sx={{ maxWidth: 160 }}
            />
          }
        />
        <SkillsPicker presetId={selected.id} />
        <Section title="Bot Strategy / Policy" sx={{ variant: 'plain', px: 0, py: 0 }}>
          <Stack spacing={1}>

            <FormControlLabel
              control={
                <Switch
                  checked={!!selected.raceIfNoGoodValue}
                  onChange={(e) => patchPreset(selected.id!, 'raceIfNoGoodValue', e.target.checked)}
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
                  checked={!!selected.prioritizeHint}
                  onChange={(e) => patchPreset(selected.id!, 'prioritizeHint', e.target.checked)}
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
        <RaceScheduler presetId={selected.id} compact={compact} />
      </Stack>
    </Section>
  )
}