import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Snackbar,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material'
import Section from '@/components/common/Section'
import { useNavPrefsStore } from '@/store/navPrefsStore'

const BANNER_SLOTS: readonly [1, 2, 3] = [1, 2, 3]

const LABEL_MAP: Record<1 | 2 | 3, string> = {
  1: 'First opponent',
  2: 'Second opponent',
  3: 'Third opponent',
}

export default function TeamTrialsPrefs() {
  const prefs = useNavPrefsStore((state) => state.prefs)
  const setTeamTrialsBanner = useNavPrefsStore((state) => state.setTeamTrialsBanner)
  const save = useNavPrefsStore((state) => state.save)
  const loading = useNavPrefsStore((state) => state.loading)
  const saving = useNavPrefsStore((state) => state.saving)
  const error = useNavPrefsStore((state) => state.error)
  const resetError = useNavPrefsStore((state) => state.resetError)
  const loaded = useNavPrefsStore((state) => state.loaded)
  const [toast, setToast] = useState<{ open: boolean; message: string; severity: 'success' | 'error' }>(
    {
      open: false,
      message: '',
      severity: 'success',
    },
  )

  const handleSelect = (_: unknown, slot: 1 | 2 | 3 | null) => {
    if (!slot) return
    setTeamTrialsBanner(slot)
    setToast((prev) => ({ ...prev, open: false }))
  }

  const handleSave = async () => {
    try {
      resetError()
      await save()
      setToast({ open: true, message: 'Team Trials preference saved', severity: 'success' })
    } catch {
      setToast({ open: true, message: 'Failed to save Team Trials preference', severity: 'error' })
    }
  }

  return (
    <Section title="Team Trials Preferences">
      <Stack spacing={2.5} alignItems="stretch">
        {(loading || saving) && <LinearProgress sx={{ borderRadius: 1 }} />}
        {!loaded && !loading ? (
          <Typography variant="body2" color="text.secondary" align="center">
            Loading preferences…
          </Typography>
        ) : (
          <Stack spacing={2}>
            <Typography variant="subtitle1" fontWeight={600}>
              Preferred opponent banner
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Choose which banner slot should be clicked automatically when Team Trials banners appear.
            </Typography>
            <ToggleButtonGroup
              exclusive
              value={prefs.team_trials.preferred_banner}
              onChange={handleSelect}
              color="primary"
              size="medium"
              sx={{ flexWrap: 'wrap' }}
            >
              {BANNER_SLOTS.map((slot) => (
                <ToggleButton key={slot} value={slot} sx={{ minWidth: 120 }}>
                  {LABEL_MAP[slot]}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Stack>
        )}
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Button
            variant="contained"
            disabled={saving || loading}
            onClick={handleSave}
            sx={{ minWidth: { xs: '100%', sm: 220 } }}
          >
            {saving ? 'Saving…' : 'Save preference'}
          </Button>
        </Box>
        {error && (
          <Alert severity="error" onClose={resetError} variant="outlined">
            {error}
          </Alert>
        )}
        <Snackbar
          open={toast.open}
          autoHideDuration={2400}
          onClose={() => setToast((prev) => ({ ...prev, open: false }))}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
          <Alert
            severity={toast.severity}
            onClose={() => setToast((prev) => ({ ...prev, open: false }))}
            variant="filled"
            sx={{ width: '100%' }}
          >
            {toast.message}
          </Alert>
        </Snackbar>
      </Stack>
    </Section>
  )
}
