import { useConfigStore } from '@/store/configStore'
import { Box, Divider, IconButton, Menu, MenuItem, Stack, Tab, Tabs, TextField, Tooltip, Typography } from '@mui/material'
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

const GROUP_COLORS = ['#42a5f5', '#ab47bc', '#26a69a', '#ffa726', '#ec407a', '#7e57c2', '#66bb6a', '#ff7043'] as const

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
  const reorderPresets = useConfigStore((s) => s.reorderPresets)
  const setPresetGroup = useConfigStore((s) => s.setPresetGroup)
  const renamePresetGroup = useConfigStore((s) => s.renamePresetGroup)
  const deletePresetGroup = useConfigStore((s) => s.deletePresetGroup)
  const addPreset = useConfigStore((s) => s.addPreset)
  const deletePreset = useConfigStore((s) => s.deletePreset)
  const copyPreset = useConfigStore((s) => s.copyPreset)
  const renamePreset = useConfigStore((s) => s.renamePreset)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [groupMenuAnchor, setGroupMenuAnchor] = useState<HTMLElement | null>(null)
  const [groupMenuPresetId, setGroupMenuPresetId] = useState<string | null>(null)
  const [groupDraft, setGroupDraft] = useState('')
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [showOnlyUngrouped, setShowOnlyUngrouped] = useState(false)
  const selected = useMemo(() => (selectedId ? presets.find((p) => p.id === selectedId) : undefined), [presets, selectedId])
  const active = useMemo(() => (activeId ? presets.find((p) => p.id === activeId) : undefined), [presets, activeId])

  const groupNames = useMemo(() => {
    const set = new Set<string>()
    for (const p of presets) {
      if (p.group) set.add(p.group)
    }
    return Array.from(set).sort()
  }, [presets])

  const groupColors = useMemo(() => {
    const map: Record<string, string> = {}
    groupNames.forEach((name, index) => {
      map[name] = GROUP_COLORS[index % GROUP_COLORS.length]
    })
    return map
  }, [groupNames])

  const visiblePresets = useMemo(() => {
    if (!presets.length) return presets
    const list = presets
    return list.filter((p) => {
      if (!p.group) return true
      if (!collapsedGroups[p.group]) return true
      return p.id === selectedId
    })
  }, [presets, collapsedGroups, selectedId])

  const handleOpenGroupMenu = useCallback(
    (event: React.MouseEvent<HTMLElement>, presetId: string) => {
      event.preventDefault()
      setGroupMenuAnchor(event.currentTarget)
      setGroupMenuPresetId(presetId)
      const preset = presets.find((p) => p.id === presetId)
      setGroupDraft(preset?.group ?? '')
    },
    [presets],
  )

  const handleCloseGroupMenu = useCallback(() => {
    setGroupMenuAnchor(null)
    setGroupMenuPresetId(null)
  }, [])

  const handleApplyGroupName = useCallback(() => {
    if (!groupMenuPresetId) return
    const preset = presets.find((p) => p.id === groupMenuPresetId)
    if (!preset) return
    const current = preset.group ?? null
    const nextName = groupDraft.trim()

    if (!current && nextName) {
      setPresetGroup(preset.id, nextName)
    } else if (current && nextName && nextName !== current) {
      renamePresetGroup(current, nextName)
    } else if (current && !nextName) {
      deletePresetGroup(current)
    }

    handleCloseGroupMenu()
  }, [groupMenuPresetId, presets, groupDraft, setPresetGroup, renamePresetGroup, deletePresetGroup, handleCloseGroupMenu])

  const handleRemoveFromGroup = useCallback(() => {
    if (!groupMenuPresetId) return
    const preset = presets.find((p) => p.id === groupMenuPresetId)
    if (!preset) return
    setPresetGroup(preset.id, null)
    handleCloseGroupMenu()
  }, [groupMenuPresetId, presets, setPresetGroup, handleCloseGroupMenu])

  const handleMoveToExistingGroup = useCallback(
    (name: string) => {
      if (!groupMenuPresetId) return
      const preset = presets.find((p) => p.id === groupMenuPresetId)
      if (!preset) return
      setPresetGroup(preset.id, name)
      handleCloseGroupMenu()
    },
    [groupMenuPresetId, presets, setPresetGroup, handleCloseGroupMenu],
  )

  const toggleGroupCollapse = useCallback((name: string) => {
    setCollapsedGroups((prev) => ({ ...prev, [name]: !prev[name] }))
  }, [])

  const handleDropOnGroup = useCallback(
    (name: string | null) => {
      if (!draggingId) return
      const preset = presets.find((p) => p.id === draggingId)
      if (!preset) return
      setPresetGroup(preset.id, name)
      setDraggingId(null)
    },
    [draggingId, presets, setPresetGroup],
  )

  const handleDropOnTab = useCallback(
    (targetId: string) => {
      if (!draggingId || draggingId === targetId) return
      const ids = presets.map((p) => p.id)
      const from = ids.indexOf(draggingId)
      const to = ids.indexOf(targetId)
      if (from === -1 || to === -1) return
      const next = [...ids]
      next.splice(from, 1)
      const insertAt = from < to ? to : to
      next.splice(insertAt, 0, draggingId)
      reorderPresets(next)
      setDraggingId(null)
    },
    [draggingId, presets, reorderPresets],
  )

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
    <Stack spacing={1}>
      {groupNames.length > 0 && (
        <Stack spacing={0.5}>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flexWrap: 'wrap' }}>
            {groupNames.map((name) => {
              const collapsed = !!collapsedGroups[name]
              const baseColor = groupColors[name]
              return (
                <Box
                  key={name}
                  onClick={() => toggleGroupCollapse(name)}
                  onDragOver={(e) => {
                    if (draggingId) e.preventDefault()
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    handleDropOnGroup(name)
                  }}
                  sx={{
                    px: 1.25,
                    py: 0.4,
                    borderRadius: 999,
                    border: '1px solid',
                    borderColor: collapsed ? 'divider' : baseColor,
                    bgcolor: collapsed ? 'background.paper' : baseColor,
                    color: collapsed ? baseColor || 'text.secondary' : 'primary.contrastText',
                    display: 'inline-flex',
                    alignItems: 'center',
                    cursor: 'pointer',
                    fontSize: 12,
                  }}
                >
                  <Box component="span" sx={{ mr: 0.75 }}>
                    {collapsed ? '▶' : '▼'}
                  </Box>
                  <Box component="span" sx={{ fontWeight: 500 }}>{name}</Box>
                </Box>
              )
            })}
            <Box
              onDragOver={(e) => {
                if (draggingId) e.preventDefault()
              }}
              onDrop={(e) => {
                e.preventDefault()
                handleDropOnGroup(null)
              }}
              onClick={() => setShowOnlyUngrouped((prev) => !prev)}
              sx={{
                px: 1.1,
                py: 0.3,
                borderRadius: 999,
                border: '1px dashed',
                borderColor: showOnlyUngrouped ? 'primary.main' : 'divider',
                bgcolor: showOnlyUngrouped ? 'primary.main' : 'transparent',
                color: showOnlyUngrouped ? 'primary.contrastText' : 'text.secondary',
                fontSize: 12,
                cursor: draggingId ? 'copy' : 'pointer',
              }}
            >
              Ungrouped
            </Box>
          </Stack>
        </Stack>
      )}

      <Typography variant="caption" color="text.secondary">
        Tip: Right-click a tab to create or rename groups. Drag tabs between groups to rearrange. Press the 'chip' to filter by only that group (you can combine multiple).
      </Typography>

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
          {visiblePresets.map((p) => {
            const color = p.group ? groupColors[p.group] : undefined
            return (
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
                draggable
                onDragStart={() => setDraggingId(p.id)}
                onDragEnd={() => setDraggingId((prev) => (prev === p.id ? null : prev))}
                onDragOver={(e) => {
                  if (draggingId && draggingId !== p.id) e.preventDefault()
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  handleDropOnTab(p.id)
                }}
                onContextMenu={(e) => handleOpenGroupMenu(e, p.id)}
                sx={{
                  textTransform: 'none',
                  fontWeight: p.id === selectedId ? 600 : 400,
                  ...(color
                    ? {
                        '&.Mui-selected': {
                          color: 'text.primary',
                        },
                        '&::after': {
                          content: '""',
                          position: 'absolute',
                          left: 12,
                          right: 12,
                          bottom: 4,
                          height: 3,
                          borderRadius: 999,
                          backgroundColor: color,
                          opacity: p.id === selectedId ? 1 : 0.5,
                        },
                      }
                    : {}),
                }}
              />
            )
          })}
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
      <Menu
        anchorEl={groupMenuAnchor}
        open={!!groupMenuAnchor}
        onClose={handleCloseGroupMenu}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
          <TextField
            label="Group name"
            size="small"
            value={groupDraft}
            onChange={(e) => setGroupDraft(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') {
                e.preventDefault()
                handleApplyGroupName()
              }
            }}
            autoFocus
          />
        </Box>
        <MenuItem onClick={handleApplyGroupName}>Apply name</MenuItem>
        <Divider />
        {groupNames.length > 0 && (
          <>
            <Box sx={{ px: 2, pt: 1, pb: 0.5, typography: 'caption', color: 'text.secondary' }}>
              Move to group
            </Box>
            {groupNames.map((name) => (
              <MenuItem key={name} onClick={() => handleMoveToExistingGroup(name)}>
                {name}
              </MenuItem>
            ))}
            <Divider />
          </>
        )}
        <MenuItem onClick={handleRemoveFromGroup} disabled={!groupMenuPresetId}>
          Remove from group
        </MenuItem>
      </Menu>
    </Stack>
  )
}
