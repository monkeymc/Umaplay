import { useState } from 'react'
import {
  Avatar,
  Box,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  FormLabel,
  IconButton,
  Stack,
  Switch,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material'
import { Info as InfoIcon, Tune as TuneIcon } from '@mui/icons-material'
import Section from '@/components/common/Section'
import { useConfigStore } from '@/store/configStore'
import FieldRow from '@/components/common/FieldRow'
import { defaultUnityCupAdvanced, STAT_KEYS } from '@/models/config.schema'
import type { UnityCupAdvancedSettings } from '@/models/types'
import UnityCupAdvancedDialog from './UnityCupAdvancedDialog'
import type { StrategyComponentProps } from './UraStrategy'

/**
 * Unity Cup-specific Bot Strategy controls
 * Currently inherits URA base logic; extend with Unity Cup-specific toggles as needed
 * (e.g., team race scheduling, explosion burst management, etc.)
 */
export default function UnityCupStrategy({ preset }: StrategyComponentProps) {
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const handleNumberChange = (key: 'weakTurnSv' | 'racePrecheckSv', value: string) => {
    const numeric = Number(value)
    if (Number.isFinite(numeric)) {
      patchPreset(preset.id!, key, Math.max(0, numeric))
    }
  }

  return (
    <Section
      title="Bot Strategy / Policy"
      sx={{ px: 0, py: 0, width: '100%', maxWidth: 'none' }}
      contentSx={{ gap: 2, width: '100%' }}
      titleSx={{ textAlign: 'center', mb: 0 }}
    >
      <Stack
        sx={{
          p: { xs: 1.75, md: 2.25 },
          width: '100%',
        }}
      >
        <Stack direction="row" justifyContent="flex-end" sx={{ mt: -1.5, mb: 0.5 }}>
          <Button
            size="small"
            variant="outlined"
            startIcon={<TuneIcon fontSize="small" />}
            onClick={() => setAdvancedOpen(true)}
          >
            Advanced scoring
          </Button>
        </Stack>

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
                label="Pre-check SV threshold"
                info="Skip races or infirmary if max training SV meets or exceeds this value during lobby pre-check."
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
                info="If the best allowed training SV is below this value. Bot could skip training and either: rest, race (if enabled), etc."
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

          {/* Unity Cup-specific spirit burst and opponent tuning, below the two core cards */}
          {(() => {
            const unityAdvanced: UnityCupAdvancedSettings =
              (preset.unityCupAdvanced as UnityCupAdvancedSettings | undefined) ?? defaultUnityCupAdvanced()

            const updateUnityAdvanced = (next: UnityCupAdvancedSettings) => {
              patchPreset(preset.id!, 'unityCupAdvanced', next as any)
            }

            const toggleStat = (stat: (typeof STAT_KEYS)[number]) => {
              const exists = unityAdvanced.burstAllowedStats.includes(stat)
              const nextStats = exists
                ? unityAdvanced.burstAllowedStats.filter((s) => s !== stat)
                : [...unityAdvanced.burstAllowedStats, stat]
              if (nextStats.length === 0) return
              updateUnityAdvanced({
                ...unityAdvanced,
                burstAllowedStats: nextStats,
              })
            }

            const updateOpponent = (
              key: keyof UnityCupAdvancedSettings['opponentSelection'],
              value: number,
            ) => {
              updateUnityAdvanced({
                ...unityAdvanced,
                opponentSelection: {
                  ...unityAdvanced.opponentSelection,
                  [key]: value,
                },
              })
            }

            const opponentOptions = [
              { value: 1, label: 'Hard' },
              { value: 2, label: 'Medium' },
              { value: 3, label: 'Easy' },
            ] as const

            const opponentFields: (keyof UnityCupAdvancedSettings['opponentSelection'])[] = [
              'race1',
              'race2',
              'race3',
              'race4',
              'defaultUnknown',
            ]

            return (
              <Box
                sx={{
                  mt: 1.5,
                  border: theme => `1px dashed ${theme.palette.divider}`,
                  borderRadius: 2,
                  p: { xs: 1.25, md: 1.5 },
                  bgcolor: 'background.paper',
                }}
              >
                <Stack spacing={1.5}>
                  <Typography variant="subtitle2" color="text.secondary">
                    Unity Cup spirit & opponent tuning
                  </Typography>

                  <Box>
                    <FormLabel component="legend">
                      <Stack direction="row" spacing={0.75} alignItems="center" justifyContent="center">
                        <Typography variant="body2">Allowed stats for blue spirit burst</Typography>
                        <Box
                          component="img"
                          src="/icons/spirit_burst.png"
                          alt="Spirit burst"
                          sx={{ width: 18, height: 18, display: 'block' }}
                        />
                      </Stack>
                    </FormLabel>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
                      Blue icons: bursts allowed. Faded icons: bursts blocked for that stat.
                    </Typography>
                    <Typography variant="caption" color="red" sx={{ display: 'block', mt: 0.25 }}>
                      Be careful, This config can cause the bot to skip multiple trainings (bad RNG). I recommend you to allow at least 2 stats.
                    </Typography>
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ mt: 0.75, flexWrap: 'wrap', justifyContent: 'center' }}
                    >
                      {STAT_KEYS.map((stat) => {
                        const selected = unityAdvanced.burstAllowedStats.includes(stat)
                        const iconMap: Record<string, string> = {
                          SPD: '/icons/support_card_type_spd.png',
                          STA: '/icons/support_card_type_sta.png',
                          PWR: '/icons/support_card_type_pwr.png',
                          GUTS: '/icons/support_card_type_guts.png',
                          WIT: '/icons/support_card_type_wit.png',
                        }
                        const src = iconMap[stat] ?? ''
                        return (
                          <Chip
                            key={stat}
                            avatar={<Avatar src={src} alt={stat} sx={{ width: 24, height: 24 }} />}
                            label={stat}
                            clickable
                            onClick={() => toggleStat(stat)}
                            variant={selected ? 'filled' : 'outlined'}
                            sx={{
                              position: 'relative',
                              overflow: 'visible',
                              backgroundImage: selected
                                ? 'linear-gradient(135deg, #4fc3f7, #1565c0)'
                                : 'none',
                              backgroundSize: selected ? '200% 200%' : undefined,
                              bgcolor: selected ? 'transparent' : 'inherit',
                              color: selected ? '#ffffff' : 'inherit',
                              opacity: selected ? 1 : 0.45,
                              textTransform: 'uppercase',
                              fontWeight: selected ? 600 : 400,
                              boxShadow: selected
                                ? '0 0 0 1px rgba(21,101,192,0.4), 0 4px 8px rgba(21,101,192,0.35)'
                                : 'none',
                              transition:
                                'box-shadow 150ms ease-out, transform 150ms ease-out, opacity 150ms ease-out',
                              '&:hover': selected
                                ? {
                                    opacity: 0.5,
                                  }
                                : {
                                    boxShadow:
                                      '0 0 0 1px rgba(8, 92, 131, 0.95), 0 0 10px rgba(129,212,250,0.9), 0 0 18px rgba(38,198,218,0.85)',
                                    transform: 'translateY(-2px)',
                                  },
                              '&::before': {
                                content: '""',
                                position: 'absolute',
                                inset: -4,
                                borderRadius: '999px',
                                backgroundImage:
                                  'radial-gradient(circle at 30% 0, rgba(129,212,250,0.9), transparent 55%), ' +
                                  'radial-gradient(circle at 70% 100%, rgba(38,198,218,0.8), transparent 60%)',
                                opacity: 0,
                                zIndex: -1,
                              },
                              '&:hover::before': {
                                opacity: 1,
                                animation: 'firePulse 1.1s ease-in-out infinite',
                              },
                              '@keyframes firePulse': {
                                '0%': { transform: 'scale(0.7)', opacity: 0.25 },
                                '50%': { transform: 'scale(1.04)', opacity: 0.95 },
                                '100%': { transform: 'scale(0.7)', opacity: 0.25 },
                              },
                              '& .MuiAvatar-root': {
                                filter: selected ? 'none' : 'grayscale(1)',
                                opacity: selected ? 1 : 0.6,
                              },
                            }}
                          />
                        )
                      })}
                    </Stack>
                  </Box>

                  <Box>
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.5 }}>
                      <Typography variant="body2">Opponent selection order</Typography>
                      <Tooltip title="Which banner slot to challenge for each Unity Cup race.">
                        <IconButton size="small" color="info">
                          <InfoIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Stack>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                      Pick Hard / Medium / Easy for each race; the bot will click the corresponding banner slot.
                    </Typography>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                      If bot can't determine the 'race number' / 'date info', it will use the fallback option.
                    </Typography>
                    <Box
                      sx={{
                        display: 'grid',
                        gap: 1,
                        gridTemplateColumns: {
                          xs: '1fr',
                          sm: 'repeat(3, minmax(0, 1fr))',
                          md: 'repeat(5, minmax(0, 1fr))',
                        },
                      }}
                    >
                      {opponentFields.map((key) => (
                        <Box key={key} sx={{ minWidth: 0 }}>
                          <FormLabel component="legend" sx={{ mb: 0.25 }}>
                            {key === 'defaultUnknown' ? 'Fallback' : `Race ${key.replace('race', '')}`}
                          </FormLabel>
                          <ToggleButtonGroup
                            exclusive
                            size="small"
                            value={unityAdvanced.opponentSelection[key]}
                            onChange={(_, val) => {
                              if (typeof val === 'number') updateOpponent(key, val)
                            }}
                            orientation="vertical"
                            sx={{ width: '100%' }}
                          >
                            {opponentOptions.map((opt) => {
                              const colorMap: Record<number, { bg: string; fg: string }> = {
                                1: { bg: '#ffeb3b', fg: '#212121' }, // yellow - hard
                                2: { bg: '#4caf50', fg: '#ffffff' }, // green - medium
                                3: { bg: '#29b6f6', fg: '#ffffff' }, // sky blue - easy
                              }
                              const c = colorMap[opt.value] ?? { bg: '#1976d2', fg: '#ffffff' }
                              return (
                                <ToggleButton
                                  key={opt.value}
                                  value={opt.value}
                                  sx={{
                                    px: 1,
                                    justifyContent: 'flex-start',
                                    '&.Mui-selected': {
                                      bgcolor: c.bg,
                                      color: c.fg,
                                      '&:hover': {
                                        bgcolor: c.bg,
                                        opacity: 0.9,
                                      },
                                    },
                                    '& .MuiTypography-root': { fontSize: '0.75rem' },
                                  }}
                                >
                                  <Typography variant="caption">{opt.label}</Typography>
                                </ToggleButton>
                              )
                            })}
                          </ToggleButtonGroup>
                        </Box>
                      ))}
                    </Box>
                  </Box>
                </Stack>
              </Box>
            )
          })()}

          {/* TODO: Add Unity Cup-specific strategy controls here:
              - Team race scheduling preferences
              - Spirit Explosion / burst management
              - etc.
          */}
        </Stack>
        {(() => {
          const currentAdvanced: UnityCupAdvancedSettings =
            (preset.unityCupAdvanced as UnityCupAdvancedSettings | undefined) ?? defaultUnityCupAdvanced()

          return (
            <UnityCupAdvancedDialog
              open={advancedOpen}
              settings={currentAdvanced}
              onClose={() => setAdvancedOpen(false)}
              onSave={(next) => {
                patchPreset(preset.id!, 'unityCupAdvanced', next as any)
                setAdvancedOpen(false)
              }}
            />
          )
        })()}
      </Stack>
    </Section>
  )
}
