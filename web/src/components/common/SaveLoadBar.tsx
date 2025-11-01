import { Button, Stack, Snackbar, Alert } from '@mui/material'
import { useConfigStore } from '@/store/configStore'
import { useEventsSetupStore } from '@/store/eventsSetupStore'
import { saveServerConfig, saveNavPrefs } from '@/services/api'
import { useNavPrefsStore } from '@/store/navPrefsStore'
import { useState } from 'react'

export default function SaveLoadBar() {
  const commitSelectedPreset = useConfigStore((s) => s.commitSelectedPreset)
  const getActivePreset = useConfigStore((s) => s.getActivePreset)
  const navPrefs = useNavPrefsStore((s) => s.prefs)
  const refreshNavPrefs = useNavPrefsStore((s) => s.load)
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
              // 1) Commit selected preset as active
              commitSelectedPreset()
              
              // 2) snapshot current Event Setup from its store
              const setup = useEventsSetupStore.getState().getSetup()

              // 3) Get updated config after commit
              const updatedConfig = useConfigStore.getState().config
              const { id: activeId, preset: activePreset } = getActivePreset()
              const presets = Array.isArray(updatedConfig?.presets) ? updatedConfig.presets : []
              const targetId = activeId || presets[0]?.id || null

              // 4) merge event_setup into that preset (no other changes)
              const merged =
                targetId
                  ? {
                      ...updatedConfig,
                      presets: presets.map((p: any) =>
                        p.id === targetId ? { ...p, event_setup: setup } : p
                      ),
                    }
                  : updatedConfig // if no presets, just send config as-is

              // 5) POST full config (your existing endpoint)
              await saveServerConfig(merged)
              await saveNavPrefs(navPrefs)

              // 6) Also update the local config store so
              //    export/import and LocalStorage see this immediately.
              useConfigStore.setState((s) => ({ ...s, config: merged }))
              refreshNavPrefs().catch(() => {
                /* ignore */
              })
              const presetName = activePreset?.name || 'Unnamed preset'
              setSnack({ open: true, msg: `Saved config with active preset: ${presetName}`, severity: 'success' })
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
