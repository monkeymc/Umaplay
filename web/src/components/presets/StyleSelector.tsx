import { MenuItem, Paper, Select, Stack, Typography } from '@mui/material'
import { useConfigStore } from '@/store/configStore'

// const STYLES = [null, 'end', 'late', 'pace', 'front'] as const

export default function StyleSelector({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.getSelectedPreset().preset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  if (!preset) return null

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1}>
        <Typography variant="subtitle2">Style to select in Debut (only triggered here, once, choose wisely)</Typography>
        <Select
          size="small"
          value={preset.juniorStyle ?? ''}
          displayEmpty
          onChange={(e) =>
            patchPreset(presetId, 'juniorStyle', (e.target.value || null) as any)
          }
          sx={{ width: 220 }}
        >
          <MenuItem value="">{'None'}</MenuItem>
          <MenuItem value="end">end</MenuItem>
          <MenuItem value="late">late</MenuItem>
          <MenuItem value="pace">pace</MenuItem>
          <MenuItem value="front">front</MenuItem>
        </Select>
      </Stack>
    </Paper>
  )
}
