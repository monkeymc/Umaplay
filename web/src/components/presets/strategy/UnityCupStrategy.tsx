import {
  FormControlLabel,
  Switch,
  IconButton,
  Tooltip,
  Typography,
  Stack,
  TextField,
  Box,
  Divider,
} from '@mui/material'
import { Info as InfoIcon } from '@mui/icons-material'
import Section from '@/components/common/Section'
import { useConfigStore } from '@/store/configStore'
import FieldRow from '@/components/common/FieldRow'
import type { StrategyComponentProps } from './UraStrategy'

/**
 * Unity Cup-specific Bot Strategy controls
 * Currently inherits URA base logic; extend with Unity Cup-specific toggles as needed
 * (e.g., team race scheduling, explosion burst management, etc.)
 */
export default function UnityCupStrategy({ preset }: StrategyComponentProps) {
  const patchPreset = useConfigStore((s) => s.patchPreset)

  const handleNumberChange = (key: 'weakTurnSv' | 'racePrecheckSv', value: string) => {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      patchPreset(preset.id!, key, Math.max(0, numeric))
    }
  }

  return (
    <Section title="Bot Strategy / Policy" sx={{ px: 0, py: 0, width: '100%', maxWidth: 'none' }} contentSx={{ gap: 2, width: '100%' }} titleSx={{ textAlign: 'center' }}>
      <Stack
        sx={{
          p: { xs: 1.75, md: 2.25 },
          width: '100%',
          }}
      >
        <Stack spacing={2}>
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
                <Tooltip title="If for example our best option is SV ≤ 1 and this toggle is enabled, the bot prefers entering a race (ideally G2/G1) to farm stats and skill points.">
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
                <Tooltip title="Give priority to hint tiles during training. Massive SV tiles still take precedence if they clearly outperform hints.">
                  <IconButton size="small" color="info">
                    <InfoIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            }
          />

          <Divider sx={{ my: 0.5 }} />

          <Box
            sx={{
              display: 'grid',
              gap: { xs: 1.25, md: 1.75 },
              gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
              alignItems: 'stretch',
              width: '100%',
            }}
          >
            <Box
              sx={{
                border: theme => `1px solid ${theme.palette.divider}`,
                borderRadius: 2,
                p: { xs: 1.25, md: 1.5 },
                bgcolor: 'background.default',
                display: 'flex',
                flexDirection: 'column',
                gap: 1.5,
                minHeight: '100%',
                boxShadow: theme => `0 1px 3px ${theme.palette.mode === 'dark' ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.04)'}`,
              }}
            >
              <Typography variant="subtitle2" color="text.secondary">
                Lobby pre-check controls
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={!!preset.lobbyPrecheckEnable}
                    onChange={(e) => patchPreset(preset.id!, 'lobbyPrecheckEnable', e.target.checked)}
                  />
                }
                label={
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <Typography variant="body1">Enable lobby pre-check</Typography>
                    <Tooltip title="Before races or infirmary, peek at training to see if a high-value tile makes skipping worthwhile.">
                      <IconButton size="small" color="info">
                        <InfoIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                }
              />
              <FieldRow
                label="Race pre-check SV threshold"
                info="Skip planned races or infirmary if training SV meets or exceeds this value during lobby pre-check."
                control={
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    inputProps={{ min: 0, step: 0.1, style: { paddingRight: '12px' } }}
                    value={preset.racePrecheckSv ?? ''}
                    onChange={(e) => handleNumberChange('racePrecheckSv', e.target.value)}
                  />
                }
              />
            </Box>

            <Box
              sx={{
                border: theme => `1px solid ${theme.palette.divider}`,
                borderRadius: 2,
                p: { xs: 1.25, md: 1.5 },
                bgcolor: 'background.default',
                display: 'flex',
                flexDirection: 'column',
                gap: 1.5,
                minHeight: '100%',
                boxShadow: theme => `0 1px 3px ${theme.palette.mode === 'dark' ? 'rgba(0,0,0,0.2)' : 'rgba(0,0,0,0.04)'}`,
              }}
            >
              <Typography variant="subtitle2" color="text.secondary">
                Training fallbacks
              </Typography>
              <FieldRow
                label="Weak turn SV threshold"
                info="If the best allowed training SV is below this value and energy is low, rest instead."
                control={
                  <TextField
                    fullWidth
                    size="small"
                    type="number"
                    inputProps={{ min: 0, step: 0.1, style: { paddingRight: '12px' } }}
                    value={preset.weakTurnSv ?? ''}
                    onChange={(e) => handleNumberChange('weakTurnSv', e.target.value)}
                  />
                }
              />
            </Box>
          </Box>

          {/* TODO: Add Unity Cup-specific strategy controls here:
              - Team race scheduling preferences
              - Spirit Explosion / burst management
              - etc.
          */}
        </Stack>
      </Stack>
    </Section>
  )
}
