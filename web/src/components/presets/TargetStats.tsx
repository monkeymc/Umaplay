import { useConfigStore } from '@/store/configStore'
import { Box, Paper, TextField, Typography, Button, Stack, InputAdornment, Avatar } from '@mui/material'
import { STAT_ICON } from '@/constants/ui'

const DEFAULTS = { SPD: 1150, STA: 770, PWR: 570, GUTS: 270, WIT: 370 }

export default function TargetStats({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.config.presets.find((p) => p.id === presetId))
  const patchPreset = useConfigStore((s) => s.patchPreset)

  if (!preset) return null
  const ts = preset.targetStats

  const set = (k: keyof typeof ts, v: number) =>
    patchPreset(presetId, 'targetStats', { ...ts, [k]: v })

  const reset = () => patchPreset(presetId, 'targetStats', { ...DEFAULTS })

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="subtitle2">Stat Caps</Typography>
        <Button size="small" onClick={reset}>Reset to defaults</Button>
      </Stack>
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: {
            xs: 'repeat(2, 1fr)',  // 2 per row on phones
            md: 'repeat(3, 1fr)',  // 3 per row on md
            lg: 'repeat(5, 1fr)',  // 5 per row on lg (one per stat)
          },
        }}
      >
        {Object.entries(ts).map(([key, val]) => (
          <TextField
            key={key}
            label={key}
            type="number"
            size="small"
            value={val}
            inputProps={{ min: 0 }}
            onChange={(e) => set(key as any, Number(e.target.value || 0))}
            fullWidth
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Avatar
                    src={STAT_ICON[key as keyof typeof STAT_ICON]}
                    alt={key}
                    sx={{ width: 20, height: 20 }}
                  />
                </InputAdornment>
              ),
            }}
          />
        ))}
      </Box>
    </Paper>
  )
}
