import { useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material'

import SmartImage from '@/components/common/SmartImage'
import type { SelectedSupport, SupportPriority } from '@/types/events'
import { supportImageCandidates, supportTypeIcons } from '@/utils/imagePaths'
import { useEventsSetupStore } from '@/store/eventsSetupStore'

const DEFAULT_PRIORITY: SupportPriority = {
  enabled: true,
  scoreBlueGreen: 0.75,
  scoreOrangeMax: 0.5,
}

type Props = {
  open: boolean
  support: SelectedSupport | null
  onClose: () => void
}

export default function SupportPriorityDialog({ open, support, onClose }: Props) {
  const setSupportPriority = useEventsSetupStore((s) => s.setSupportPriority)
  const slot = support?.slot ?? -1
  const current = useMemo<SupportPriority>(() => {
    if (!support?.priority) return DEFAULT_PRIORITY
    return {
      enabled: support.priority.enabled,
      scoreBlueGreen: support.priority.scoreBlueGreen,
      scoreOrangeMax: support.priority.scoreOrangeMax,
    }
  }, [support])

  const [enabled, setEnabled] = useState(current.enabled)
  const [scoreBlueGreen, setScoreBlueGreen] = useState<number>(current.scoreBlueGreen)
  const [scoreOrangeMax, setScoreOrangeMax] = useState<number>(current.scoreOrangeMax)

  useEffect(() => {
    setEnabled(current.enabled)
    setScoreBlueGreen(current.scoreBlueGreen)
    setScoreOrangeMax(current.scoreOrangeMax)
  }, [current])

  const handleSave = () => {
    if (!support || slot < 0) {
      onClose()
      return
    }
    const next: SupportPriority = {
      enabled,
      scoreBlueGreen: clamp(scoreBlueGreen, 0, 10),
      scoreOrangeMax: clamp(scoreOrangeMax, 0, 10),
    }
    setSupportPriority(slot, next)
    onClose()
  }

  const handleReset = () => {
    const defaults = DEFAULT_PRIORITY
    setEnabled(defaults.enabled)
    setScoreBlueGreen(defaults.scoreBlueGreen)
    setScoreOrangeMax(defaults.scoreOrangeMax)
  }

  const ready = Boolean(support)

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Hint priority</DialogTitle>
      <DialogContent dividers>
        {!ready && (
          <Typography variant="body2">Select a support card to configure.</Typography>
        )}
        {ready && (
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
              <Box sx={{ display: 'grid', placeItems: 'center' }}>
                <Box sx={{ position: 'relative', borderRadius: 1, p: '2px', bgcolor: 'background.paper' }}>
                  <SmartImage
                    candidates={supportImageCandidates(support!.name, support!.rarity, support!.attribute)}
                    alt={support!.name}
                    width={96}
                    height={128}
                    rounded={8}
                  />
                  <Box sx={{ position: 'absolute', top: 4, left: 4, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid', borderColor: 'divider', p: '1px' }}>
                    <img src={supportTypeIcons[support!.attribute]} width={18} height={18} />
                  </Box>
                </Box>
              </Box>
              <Stack spacing={0.5} sx={{ textAlign: { xs: 'center', sm: 'left' }, width: '100%' }}>
                <Typography variant="subtitle1">{support?.name}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {support?.attribute} · {support?.rarity}
                </Typography>
              </Stack>
            </Stack>
            <FormControlLabel
              control={
                <Switch
                  checked={!enabled}
                  onChange={(e) => setEnabled(!e.target.checked)}
                />
              }
              label="Ignore hint"
            />
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Blue / Green hint value
                </Typography>
                <TextField
                  type="number"
                  size="small"
                  fullWidth
                  disabled={!enabled}
                  inputProps={{ step: 0.05, min: 0, max: 10 }}
                  value={scoreBlueGreen}
                  onChange={(e) => setScoreBlueGreen(Number(e.target.value))}
                />
              </Box>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Orange / Max hint value
                </Typography>
                <TextField
                  type="number"
                  size="small"
                  fullWidth
                  disabled={!enabled}
                  inputProps={{ step: 0.05, min: 0, max: 10 }}
                  value={scoreOrangeMax}
                  onChange={(e) => setScoreOrangeMax(Number(e.target.value))}
                />
              </Box>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Values are applied on top of the base scoring rules. Set to zero to ignore specific hint colors when enabled.
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleReset} color="inherit" disabled={!ready}>Reset to default</Button>
        <Button onClick={onClose} color="inherit">Cancel</Button>
        <Button onClick={handleSave} variant="contained" disabled={!ready}>Save</Button>
      </DialogActions>
    </Dialog>
  )
}

const clamp = (value: number, min: number, max: number) => {
  if (!Number.isFinite(value)) return min
  return Math.min(max, Math.max(min, value))
}
