import { FormControlLabel, Switch, IconButton, Tooltip, Typography, Stack } from '@mui/material'
import { Info as InfoIcon } from '@mui/icons-material'
import Section from '@/components/common/Section'
import { useConfigStore } from '@/store/configStore'
import type { StrategyComponentProps } from './UraStrategy'

/**
 * Unity Cup-specific Bot Strategy controls
 * Currently inherits URA base logic; extend with Unity Cup-specific toggles as needed
 * (e.g., team race scheduling, explosion burst management, etc.)
 */
export default function UnityCupStrategy({ preset }: StrategyComponentProps) {
  const patchPreset = useConfigStore((s) => s.patchPreset)

  return (
    <Section title="Bot Strategy / Policy" sx={{ variant: 'plain', px: 0, py: 0 }}>
      <Stack spacing={1}>
        <FormControlLabel
          control={
            <Switch
              checked={!!preset.raceIfNoGoodValue}
              onChange={(e) => patchPreset(preset.id!, 'raceIfNoGoodValue', e.target.checked)}
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
              checked={!!preset.prioritizeHint}
              onChange={(e) => patchPreset(preset.id!, 'prioritizeHint', e.target.checked)}
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

        {/* TODO: Add Unity Cup-specific strategy controls here:
            - Team race scheduling preferences
            - Spirit Explosion / burst management
            - etc.
        */}
      </Stack>
    </Section>
  )
}
