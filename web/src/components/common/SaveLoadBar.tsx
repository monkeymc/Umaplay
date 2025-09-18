import { Button, Stack, Snackbar, Alert } from '@mui/material'
import { useConfigStore } from '@/store/configStore'
import { saveServerConfig } from '@/services/api'
import { useState } from 'react'

export default function SaveLoadBar() {
   const config = useConfigStore((s) => s.config)
  // const exportJson = useConfigStore((s) => s.exportJson)
  const [saving, setSaving] = useState(false)
  const [snack, setSnack] = useState<{ open: boolean; msg: string; severity: 'success'|'error'}>({
    open: false, msg: '', severity: 'success'
  })
  return (
    <>
      <Stack direction="row" spacing={1} justifyContent="center">
        <Button
          variant="contained"
          disabled={saving}
          onClick={async () => {
            try {
              setSaving(true)
              await saveServerConfig(config)
              setSnack({ open: true, msg: 'Config saved to server (config.json)', severity: 'success' })
            } catch (e: any) {
              setSnack({ open: true, msg: e?.message ?? 'Failed to save config', severity: 'error' })
            } finally {
              setSaving(false)
            }
          }}
        >
          {saving ? 'Saving…' : 'Save config'}
        </Button>
      </Stack>
      <Snackbar
        open={snack.open}
        autoHideDuration={2200}
        onClose={() => setSnack(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setSnack(s => ({ ...s, open: false }))}
          severity={snack.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {snack.msg}
        </Alert>
      </Snackbar>
    </>
  )
}
