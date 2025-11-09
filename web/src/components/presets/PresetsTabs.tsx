import { useConfigStore } from '@/store/configStore'
import { IconButton, Stack, Tab, Tabs, TextField, Tooltip } from '@mui/material'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import AddIcon from '@mui/icons-material/Add'
import DownloadIcon from '@mui/icons-material/Download'
import UploadIcon from '@mui/icons-material/Upload'
import { useCallback, useMemo, useState } from 'react'
import { presetSchema } from '@/models/config.schema'
import { openJsonFile } from '@/services/file'
import type { Preset, ScenarioConfig } from '@/models/types'

const normalizeScenario = (value?: string | null): 'ura' | 'unity_cup' =>
  value === 'unity_cup' ? 'unity_cup' : 'ura'

export default function PresetsTabs() {
  const uiScenarioKey = useConfigStore((s) => s.uiScenarioKey)
  const uiSelectedPresetId = useConfigStore((s) => s.uiSelectedPresetId)
  const generalActiveScenario = useConfigStore((s) => s.config.general?.activeScenario)
  const scenarios = useConfigStore((s) => s.config.scenarios)

  const scenarioKey = normalizeScenario(uiScenarioKey ?? generalActiveScenario)

  const branch = useMemo(() => {
    const map = (scenarios ?? {}) as Record<string, ScenarioConfig>
    const raw = map[scenarioKey] ?? { presets: [], activePresetId: undefined }
    const presets: Preset[] = Array.isArray(raw.presets) ? (raw.presets as Preset[]) : []
    const activePresetId = raw.activePresetId && presets.some((p) => p.id === raw.activePresetId)
      ? raw.activePresetId
      : presets[0]?.id
    return { presets, activePresetId }
  }, [scenarios, scenarioKey])

  const presets = branch.presets
  const activeId = branch.activePresetId
  const selectedId = useMemo(() => {
    if (uiSelectedPresetId && presets.some((p) => p.id === uiSelectedPresetId)) {
      return uiSelectedPresetId
    }
    return activeId
  }, [uiSelectedPresetId, presets, activeId])

  const setSelectedPresetId = useConfigStore((s) => s.setSelectedPresetId)
  const addPreset = useConfigStore((s) => s.addPreset)
  const deletePreset = useConfigStore((s) => s.deletePreset)
  const copyPreset = useConfigStore((s) => s.copyPreset)
  const renamePreset = useConfigStore((s) => s.renamePreset)
  const [editingId, setEditingId] = useState<string | null>(null)
  const selected = useMemo(() => (selectedId ? presets.find((p) => p.id === selectedId) : undefined), [presets, selectedId])
  const active = useMemo(() => (activeId ? presets.find((p) => p.id === activeId) : undefined), [presets, activeId])

  const appendPreset = useCallback((preset: Preset) => {
    useConfigStore.setState((s) => {
      const scenarioKey = s.uiScenarioKey ?? s.config.general?.activeScenario ?? 'ura'
      const map = { ...(s.config.scenarios ?? {}) }
      const branch = map[scenarioKey] ?? { presets: [], activePresetId: undefined }
      const branchPresets = Array.isArray(branch.presets) ? branch.presets : []
      const presets = [...branchPresets, preset]
      map[scenarioKey] = {
        ...branch,
        presets,
        activePresetId: preset.id,
      }
      return {
        config: {
          ...s.config,
          scenarios: map,
        },
        uiSelectedPresetId: preset.id,
      }
    })
  }, [])

  const exportPreset = () => {
    if (!selected) return
    const data = JSON.parse(JSON.stringify(selected))
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const fileName = selected.name || active?.name || 'preset'
    a.download = `${fileName}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const importPreset = async () => {
    const raw: any = await openJsonFile()
    if (!raw) return
    try {
      raw.id = `${raw.id ?? 'preset'}_i`
      raw.name = `${raw.name ?? 'Preset'}_i`
      const safe = presetSchema.parse(raw)
      appendPreset(safe)
    } catch (e: any) {
      alert('Invalid preset JSON')
    }
  }

  // Cleaner: expose an injection to add exact preset
  ;(window as any)._uma_addPreset = (p: Preset) => appendPreset(p)
  return (
    <Stack spacing={1.5}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ flexWrap: 'wrap' }}>
        <Tabs
          value={selectedId ?? false}
          onChange={(_, v) => typeof v === 'string' ? setSelectedPresetId(v) : undefined}
          variant="scrollable"
          scrollButtons="auto"
          TabIndicatorProps={{ sx: { transition: 'transform 140ms ease-out !important' } }}
          sx={{
            flex: 1,
            minHeight: 44,
            '& .MuiTabs-indicator': {
              transition: 'transform 140ms ease-out, width 140ms ease-out !important',
            },
          }}
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
                  p.name + (p.id === activeId ? ' • Active' : '')
                )
              }
              onDoubleClick={() => setEditingId(p.id)}
              sx={{
                textTransform: 'none',
                fontWeight: p.id === selectedId ? 600 : 400,
              }}
            />
          ))}
        </Tabs>

        <Tooltip title="Add preset">
          <IconButton onClick={addPreset}><AddIcon /></IconButton>
        </Tooltip>

        <Tooltip title="Copy preset">
          <span>
            <IconButton disabled={!selected} onClick={() => selected && copyPreset(selected.id)}>
              <ContentCopyIcon />
            </IconButton>
          </span>
        </Tooltip>

        <Tooltip title="Delete preset">
          <span>
            <IconButton disabled={!selected} onClick={() => selected && deletePreset(selected.id)}>
              <DeleteOutlineIcon />
            </IconButton>
          </span>
        </Tooltip>

        {/* Per-preset share/import */}
        <Tooltip title="Export this preset">
          <span>
            <IconButton disabled={!selected} onClick={exportPreset}><DownloadIcon /></IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Import preset (adds as new)">
          <IconButton onClick={importPreset}><UploadIcon /></IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  )
}
