import { Fragment, useMemo, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Divider,
  LinearProgress,
  List,
  ListItem,
  Snackbar,
  Stack,
  Switch,
  Typography,
} from '@mui/material'
import Section from '@/components/common/Section'
import { useNavPrefsStore } from '@/store/navPrefsStore'

export default function ShopPrefs() {
  const prefs = useNavPrefsStore((state) => state.prefs)
  const toggleShop = useNavPrefsStore((state) => state.toggleShop)
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

  const handleToggle = (key: 'alarm_clock' | 'star_pieces' | 'parfait') => (event: React.ChangeEvent<HTMLInputElement>) => {
    toggleShop(key, event.target.checked)
    setToast((prev) => ({ ...prev, open: false }))
  }

  const handleSave = async () => {
    try {
      resetError()
      await save()
      setToast({ open: true, message: 'Preferences saved', severity: 'success' })
    } catch {
      setToast({ open: true, message: 'Failed to save preferences', severity: 'error' })
    }
  }

  const options = useMemo(
    () => [
      {
        key: 'alarm_clock' as const,
        label: 'Exchange alarm clock',
        icon: '/icons/shop_clock.png',
      },
      {
        key: 'star_pieces' as const,
        label: 'Exchange star pieces',
        icon: '/icons/shop_star_pieces.png',
      },
      {
        key: 'parfait' as const,
        label: 'Exchange parfait',
        icon: '/icons/shop_parfait.png',
      },
    ],
    [],
  )

  return (
    <Section title="Shop Preferences">
      <Stack spacing={2.5} alignItems="stretch">
        {(loading || saving) && <LinearProgress sx={{ borderRadius: 1 }} />}
        {!loaded && !loading ? (
          <Typography variant="body2" color="text.secondary" align="center">
            Loading preferences…
          </Typography>
        ) : (
          <List disablePadding>
            {options.map((item, idx) => (
              <Fragment key={item.key}>
                <ListItem sx={{ px: 0 }}>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    alignItems={{ xs: 'flex-start', sm: 'center' }}
                    justifyContent="space-between"
                    spacing={{ xs: 2, sm: 3 }}
                    sx={{ width: '100%' }}
                  >
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Box
                        component="img"
                        src={item.icon}
                        alt={item.label}
                        sx={{ width: 64, height: 64, objectFit: 'contain' }}
                      />
                      <Typography variant="subtitle1" fontWeight={600}>
                        {item.label}
                      </Typography>
                    </Stack>
                    <Switch
                      edge="end"
                      checked={prefs.shop[item.key]}
                      onChange={handleToggle(item.key)}
                      inputProps={{ 'aria-label': item.label }}
                    />
                  </Stack>
                </ListItem>
                {idx < options.length - 1 && <Divider sx={{ my: 2 }} />}
              </Fragment>
            ))}
          </List>
        )}
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Button
            variant="contained"
            disabled={saving || loading}
            onClick={handleSave}
            sx={{ minWidth: { xs: '100%', sm: 220 } }}
          >
            {saving ? 'Saving…' : 'Save preferences'}
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
