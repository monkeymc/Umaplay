import { Button, Stack, Snackbar, Alert } from '@mui/material'
import { useConfigStore } from '@/store/configStore'
import { useEventsSetupStore } from '@/store/eventsSetupStore'
import { saveServerConfig } from '@/services/api'
import { useState } from 'react'

export default function SaveLoadBar() {
   const config = useConfigStore((s) => s.config)
  // optional selectors if you keep an active preset id in configStore:
  const activePresetId = useConfigStore((s: any) => s.activePresetId || s.currentPresetId)
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
              // 1) snapshot current Event Setup from its store
              const setup = useEventsSetupStore.getState().getSetup()

              // 2) decide which preset we will attach to
              const presets = Array.isArray((config as any)?.presets) ? (config as any).presets : []
              const targetId =
                activePresetId ||
                (presets[0]?.id ?? null)

              // 3) merge event_setup into that preset (no other changes)
              const merged =
                targetId
                  ? {
                      ...config,
                      presets: presets.map((p: any) =>
                        p.id === targetId ? { ...p, event_setup: setup } : p
                      ),
                    }
                  : config // if no presets, just send config as-is

              // 4) POST full config (your existing endpoint)
              await saveServerConfig(merged)
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
