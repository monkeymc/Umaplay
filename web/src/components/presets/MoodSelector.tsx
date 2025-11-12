import {
  Box,
  Paper,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  Select,
  MenuItem,
} from '@mui/material'
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
  const preset = useConfigStore((s) => s.getSelectedPreset().preset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  if (!preset) return null

  const setMood = (_: any, v: MoodName | null) => {
    if (v) patchPreset(presetId, 'minimalMood', v)
  }

  const juniorMoodValue: MoodName | '' = (preset.juniorMinimalMood ?? '') as MoodName | ''
  const handleJuniorMood = (value: MoodName | '') => {
    patchPreset(presetId, 'juniorMinimalMood', value === '' ? null : value)
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Minimal mood</Typography>
      <Box
        sx={{
          display: 'grid',
          gap: 1.5,
          gridTemplateColumns: { xs: '1fr', md: '1fr auto' },
          alignItems: 'start',
        }}
      >
        <ToggleButtonGroup exclusive value={preset.minimalMood} onChange={setMood}>
          {MOODS.map((m) => {
            const selected = preset.minimalMood === m
            return (
              <ToggleButton
                key={m}
                value={m}
                sx={{
                  px: 0.5,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  opacity: selected ? 1 : 0.5,
                  transition: 'opacity 120ms',
                }}
              >
                {moodImgs[m] ? (
                  <Box component="img" src={moodImgs[m]} alt={m} sx={{ width: '100%', maxWidth: 80, display: 'block' }} />
                ) : (
                  m
                )}
              </ToggleButton>
            )
          })}
        </ToggleButtonGroup>
        <Box
          sx={{
            border: theme => `1px solid ${theme.palette.divider}`,
            borderRadius: 2,
            p: 1,
            minWidth: { xs: '100%', md: 220 },
            bgcolor: 'background.default',
          }}
        >
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
            Junior-year override
          </Typography>
          <Select
            size="small"
            fullWidth
            value={juniorMoodValue}
            onChange={(e) => handleJuniorMood(e.target.value as MoodName | '')}
            displayEmpty
          >
            <MenuItem value="">
              <Box component="span" sx={{ color: 'text.secondary' }}>
                Inherit preset minimal mood
              </Box>
            </MenuItem>
            {MOODS.map((mood) => (
              <MenuItem key={mood} value={mood}>
                {mood}
              </MenuItem>
            ))}
          </Select>
        </Box>
      </Box>
    </Paper>
  )
}
