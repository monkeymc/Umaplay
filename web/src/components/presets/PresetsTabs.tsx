import { useConfigStore } from '@/store/configStore'
import { IconButton, Stack, Tab, Tabs, TextField, Tooltip } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import AddIcon from '@mui/icons-material/Add'
import DownloadIcon from '@mui/icons-material/Download'
import UploadIcon from '@mui/icons-material/Upload'
import { useState } from 'react'
import { presetSchema } from '@/models/config.schema'
import { openJsonFile } from '@/services/file'

export default function PresetsTabs() {
  const { config, setActivePresetId, addPreset, deletePreset, copyPreset, renamePreset, patchPreset } = useConfigStore()
  const presets = config.presets
  const activeId = config.activePresetId ?? presets[0]?.id
  const [editingId, setEditingId] = useState<string | null>(null)
  const active = presets.find((p) => p.id === activeId)

  const exportPreset = () => {
    if (!active) return
    const data = JSON.parse(JSON.stringify(active))
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${active.name || 'preset'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importPreset = async () => {
    const raw = await openJsonFile()
    if (!raw) return
    try {
      const safe = presetSchema.parse(raw)
      // add as new preset
      patchPreset(safe.id, 'name', safe.name) // ensure fields exist (no-op if id not in list)
      // If id doesn't exist, simply append:
      // We'll reuse addPreset/copyPreset logic: quick append
      // Better: call store directly
      ;(window as any)._uma_addPreset?.(safe) // hack fallback – will be replaced by store method below
    } catch (e: any) {
      alert('Invalid preset JSON')
    }
  }

  // Cleaner: expose an injection to add exact preset
  ;(window as any)._uma_addPreset = (p: any) => {
    useConfigStore.setState((s) => ({
      config: { ...s.config, presets: [...s.config.presets, p], activePresetId: p.id },
    }))
  }
  return (
    <Stack spacing={1.5}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ flexWrap: 'wrap' }}>
        <Tabs
          value={activeId}
          onChange={(_, v) => setActivePresetId(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ flex: 1, minHeight: 44 }}
        >
          {presets.map((p) => (
            <Tab
              key={p.id}
              value={p.id}
              label={
                editingId === p.id ? (
                  <TextField
                    size="small"
                    value={p.name}
                    onChange={(e) => renamePreset(p.id, e.target.value)}
                    onBlur={() => setEditingId(null)}
                    onKeyDown={(e) => e.key === 'Enter' && setEditingId(null)}
                    autoFocus
                  />
                ) : (
                  p.name
                )
              }
              onDoubleClick={() => setEditingId(p.id)}
              sx={{ textTransform: 'none' }}
            />
          ))}
        </Tabs>

        <Tooltip title="Add preset">
          <IconButton onClick={addPreset}><AddIcon /></IconButton>
        </Tooltip>

        <Tooltip title="Copy preset">
          <span>
            <IconButton disabled={!active} onClick={() => active && copyPreset(active.id)}>
              <ContentCopyIcon />
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Delete preset">
          <span>
            <IconButton disabled={!active} onClick={() => active && deletePreset(active.id)}>
              <DeleteOutlineIcon />
            </IconButton>
          </span>
        </Tooltip>

        {/* Per-preset share/import */}
        <Tooltip title="Export this preset">
          <span>
            <IconButton disabled={!active} onClick={exportPreset}><DownloadIcon /></IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Import preset (adds as new)">
          <IconButton onClick={importPreset}><UploadIcon /></IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  )
}
