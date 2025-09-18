import { Box, Paper, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { useConfigStore } from '@/store/configStore'
import type { MoodName } from '@/models/types'

// Optional: drop mood images into src/assets/mood/*.png with these names
const moodImgs: Partial<Record<MoodName, string>> = {
  AWFUL: '/mood/awful.png',
  BAD: '/mood/bad.png',
  NORMAL: '/mood/normal.png',
  GOOD: '/mood/good.png',
  GREAT: '/mood/great.png',
}

const MOODS: MoodName[] = ['AWFUL', 'BAD', 'NORMAL', 'GOOD', 'GREAT']

export default function MoodSelector({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.config.presets.find((p) => p.id === presetId))
  const patchPreset = useConfigStore((s) => s.patchPreset)
  if (!preset) return null

  const setMood = (_: any, v: MoodName | null) => {
    if (v) patchPreset(presetId, 'minimalMood', v)
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Minimal mood</Typography>
      <ToggleButtonGroup exclusive value={preset.minimalMood} onChange={setMood}>
        {MOODS.map((m) => {
          const selected = preset.minimalMood === m
          return (
            <ToggleButton
              key={m}
              value={m}
              sx={{
                px: 1.5,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                opacity: selected ? 1 : 0.5,
                transition: 'opacity 120ms',
              }}
            >
              {moodImgs[m] ? (
                <Box component="img" src={moodImgs[m]} alt={m} sx={{ height: 28, display: 'block' }} />
              ) : (
                m
              )}
            </ToggleButton>
          )
        })}
      </ToggleButtonGroup>
    </Paper>
  )
}
