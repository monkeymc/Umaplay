import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'

import { defaultUnityCupAdvanced } from '@/models/config.schema'
import type { UnityCupAdvancedSettings } from '@/models/types'

type Props = {
  open: boolean
  settings: UnityCupAdvancedSettings
  onClose: () => void
  onSave: (next: UnityCupAdvancedSettings) => void
}

type ScoreKey = keyof UnityCupAdvancedSettings['scores']

type MultiplierGroup = keyof UnityCupAdvancedSettings['multipliers']

type MultiplierKey = keyof UnityCupAdvancedSettings['multipliers'][MultiplierGroup]

const SCORE_FIELDS: { key: ScoreKey; label: string; helper?: string }[] = [
  { key: 'rainbowCombo', label: 'Rainbow combo (per extra rainbow)' },
  { key: 'whiteSpiritFill', label: 'White spirit (filling)' },
  { key: 'whiteSpiritExploded', label: 'White spirit (exploded)' },
  { key: 'whiteComboPerFill', label: 'White combo per filling' },
  { key: 'blueSpiritEach', label: 'Blue spirit (each)' },
  { key: 'blueComboPerExtraFill', label: 'Blue combo per extra fill' },
]

const MULTIPLIER_GROUPS: { group: MultiplierGroup; title: string }[] = [
  { group: 'juniorClassic', title: 'Junior / Classic' },
  { group: 'senior', title: 'Senior' },
]

const MULTIPLIER_FIELDS: { key: MultiplierKey; label: string }[] = [
  { key: 'white', label: 'White spirits' },
  { key: 'whiteCombo', label: 'White combos' },
  { key: 'blueCombo', label: 'Blue combos' },
]

function cloneSettings(settings: UnityCupAdvancedSettings): UnityCupAdvancedSettings {
  return {
    burstAllowedStats: [...settings.burstAllowedStats],
    scores: { ...settings.scores },
    multipliers: {
      juniorClassic: { ...settings.multipliers.juniorClassic },
      senior: { ...settings.multipliers.senior },
    },
    opponentSelection: { ...settings.opponentSelection },
  }
}

export default function UnityCupAdvancedDialog({ open, settings, onClose, onSave }: Props) {
  const [draft, setDraft] = useState<UnityCupAdvancedSettings>(() => cloneSettings(settings))

  useEffect(() => {
    if (open) {
      setDraft(cloneSettings(settings))
    }
  }, [open, settings])

  const updateScore = (key: ScoreKey, value: string) => {
    const numeric = Number(value)
    setDraft(prev => {
      const next = cloneSettings(prev)
      next.scores[key] = Number.isFinite(numeric) ? numeric : prev.scores[key]
      return next
    })
  }

  const updateMultiplier = (group: MultiplierGroup, key: MultiplierKey, value: string) => {
    const numeric = Number(value)
    setDraft(prev => {
      const next = cloneSettings(prev)
      next.multipliers[group][key] = Number.isFinite(numeric) ? numeric : prev.multipliers[group][key]
      return next
    })
  }

  const handleReset = () => {
    setDraft(defaultUnityCupAdvanced())
  }

  const handleSave = () => {
    onSave(cloneSettings(draft))
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>Unity Cup Advanced Settings</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={3}>
          <Box>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle1">Scoring weights</Typography>
              <Tooltip title="Adjust individual contributions for spirits and combos.">
                <IconButton size="small">
                  <InfoOutlinedIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            </Stack>
            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                  md: 'repeat(3, minmax(0, 1fr))',
                },
              }}
            >
              {SCORE_FIELDS.map(({ key, label, helper }) => (
                <TextField
                  key={key}
                  label={label}
                  type="number"
                  value={draft.scores[key]}
                  onChange={event => updateScore(key, event.target.value)}
                  size="small"
                  inputProps={{ step: 0.05, min: 0, max: 10 }}
                  helperText={helper}
                  fullWidth
                />
              ))}
            </Box>
          </Box>

          <Box>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>Season multipliers</Typography>
            <Box
              sx={{
                display: 'grid',
                gap: 2,
                gridTemplateColumns: {
                  xs: '1fr',
                  md: 'repeat(2, minmax(0, 1fr))',
                },
              }}
            >
              {MULTIPLIER_GROUPS.map(({ group, title }) => (
                <Box
                  key={group}
                  sx={{
                    border: theme => `1px solid ${theme.palette.divider}`,
                    borderRadius: 2,
                    p: 2,
                  }}
                >
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>{title}</Typography>
                  <Box
                    sx={{
                      display: 'grid',
                      gap: 2,
                      gridTemplateColumns: {
                        xs: '1fr',
                        sm: 'repeat(3, minmax(0, 1fr))',
                      },
                    }}
                  >
                    {MULTIPLIER_FIELDS.map(({ key, label }) => (
                      <TextField
                        key={key}
                        label={label}
                        type="number"
                        value={draft.multipliers[group][key]}
                        onChange={event => updateMultiplier(group, key, event.target.value)}
                        size="small"
                        inputProps={{ step: 0.05, min: 0, max: 10 }}
                        fullWidth
                      />
                    ))}
                  </Box>
                </Box>
              ))}
            </Box>
          </Box>

          {/* Burst allowlist and opponent selection are now configured in the main Unity Cup strategy section. */}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleReset} color="inherit">Reset to defaults</Button>
        <Box sx={{ flexGrow: 1 }} />
        <Button onClick={onClose} color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained">
          Save
        </Button>
      </DialogActions>
    </Dialog>
  )
}
