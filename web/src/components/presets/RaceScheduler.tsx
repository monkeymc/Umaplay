import {
  Box,
  Paper,
  Stack,
  TextField,
  Typography,
  List,
  ListItemButton,
  ListItemText,
  Chip,
  IconButton,
  Switch,
  Tooltip,
} from '@mui/material'
import DeleteIcon from '@mui/icons-material/Delete'
import SearchIcon from '@mui/icons-material/Search'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchRaces } from '@/services/api'
import type { RacesMap, RaceInstance } from '@/models/datasets'
import { toDateKey } from '@/utils/race'
import { useConfigStore } from '@/store/configStore'
import { BADGE_ICON, DEFAULT_RACE_BANNER } from '@/constants/ui'

type RaceRow = { raceName: string; instance: RaceInstance; dateKey: string }

export default function RaceScheduler({ presetId }: { presetId: string; compact?: boolean }) {
  const preset = useConfigStore((s) => s.getSelectedPreset().preset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const { data: races = {} as RacesMap } = useQuery({ queryKey: ['races'], queryFn: fetchRaces })

  const [q, setQ] = useState('')

  if (!preset) return null

  const flat: RaceRow[] = useMemo(() => {
    const out: RaceRow[] = []
    for (const [name, arr] of Object.entries(races)) {
      for (const inst of arr) {
        const dk = toDateKey(inst.year_int, inst.month, inst.day)
        out.push({ raceName: name, instance: inst, dateKey: dk })
      }
    }
    return out
  }, [races])

  const filtered = useMemo(() => {
    const x = q.trim().toLowerCase()
    if (!x) return flat
    return flat.filter(r =>
      r.raceName.toLowerCase().includes(x) ||
      r.instance.location?.toLowerCase().includes(x) ||
      r.instance.rank.toLowerCase().includes(x) ||
      r.instance.distance_category.toLowerCase().includes(x)
    )
  }, [flat, q])

  const add = (row: RaceRow) => {
    patchPreset(presetId, 'plannedRaces', { ...preset.plannedRaces, [row.dateKey]: row.raceName })
  }

  const remove = (dateKey: string) => {
    const next = { ...preset.plannedRaces }
    delete next[dateKey]
    patchPreset(presetId, 'plannedRaces', next)
  }

  const toggleTentative = (dateKey: string) => {
    const next = { ...(preset.plannedRacesTentative ?? {}) }
    if (next[dateKey]) {
      delete next[dateKey]
    } else {
      next[dateKey] = true
    }
    patchPreset(presetId, 'plannedRacesTentative', Object.keys(next).length ? next : {})
  }

  const selectedRows: RaceRow[] = useMemo(() => {
    const list: RaceRow[] = []
    for (const [dk, name] of Object.entries(preset.plannedRaces)) {
      // Try to find a matching row for pretty display (optional)
      const r = flat.find(x => x.dateKey === dk && x.raceName === name)
      if (r) list.push(r)
      else list.push({
        dateKey: dk,
        raceName: name,
        instance: { year_int: 0, year_label: '', date_text: '', month: 0, day: 0, surface: '', distance_category: '', distance_text: '', distance_m: 0, rank: '' },
      })
    }
    return list.sort((a, b) => a.dateKey.localeCompare(b.dateKey))
  }, [preset.plannedRaces, flat])

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack spacing={1.5}>
        <Typography variant="subtitle2">Race Scheduler</Typography>

        <TextField
          size="small"
          placeholder="Search race, location, rank, distance..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          InputProps={{ startAdornment: <SearchIcon sx={{ mr: 1 }} /> as any }}
        />

        <Box
          sx={{
            display: 'grid',
            gap: 1,
            gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' },
            alignItems: 'start',
          }}
        >
          {/* Results */}
          <Paper variant="outlined" sx={{ p: 1, maxHeight: 360, overflow: 'auto' }}>
            <Typography variant="caption" color="text.secondary">
              {filtered.length} results
            </Typography>
            <List dense>
              {filtered.slice(0, 500).map((r) => {
                const badge = BADGE_ICON[r.instance.rank] || null

                // prefer race_url (new), then public_banner_path, else default
                const banner = (r.instance as any).race_url || r.instance.public_banner_path || DEFAULT_RACE_BANNER
                return (
                  <ListItemButton
                    key={`${r.dateKey}-${r.raceName}`}
                    onClick={() => add(r)}
                    sx={{ alignItems: 'center', gap: 1 }}
                  >
                    <Box
                      component="img"
                      src={banner}
                      alt=""
                      sx={{
                        width: 56,
                        height: 28,
                        objectFit: 'cover',
                        borderRadius: 0.5,
                        mr: 1,
                        display: 'block',
                        alignSelf: 'center',
                      }}
                    />
                    
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <span>{r.raceName}</span>
                          {badge && <Box component="img" src={badge} alt={r.instance.rank} sx={{ height: 18 }} />}
                        </Box>
                      }
                      secondary={`${r.instance.year_label} — ${r.instance.date_text} — ${r.instance.location ?? ''} — ${r.instance.distance_text}`}
                    />
                    <Chip size="small" label={r.dateKey} />
                  </ListItemButton>
                )
              })}
              {!filtered.length && (
                <Typography variant="caption" color="text.secondary">No results. Is /api/races available?</Typography>
              )}
            </List>
          </Paper>

          {/* Selected */}
          <Paper variant="outlined" sx={{ p: 1, maxHeight: 360, overflow: 'auto' }}>
            <Typography variant="caption" color="text.secondary">
              {selectedRows.length} selected
            </Typography>
            <List dense>
              {selectedRows.map((r) => {
                const badge = BADGE_ICON[r.instance.rank] || null
                const banner = (r.instance as any).race_url || r.instance.public_banner_path || DEFAULT_RACE_BANNER
                // Pretty date: prefer instance data, fallback to dateKey (Y{n}-{MM}-{half})
                const prettyDate =
                  (r.instance.year_label && r.instance.date_text)
                    ? `${r.instance.year_label} — ${r.instance.date_text}`
                    : (() => {
                        const [, y, mm, half] = /Y(\d+)-(\d+)-([12])/.exec(r.dateKey) || []
                        const MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']
                        const yearLabel = y === '1' ? 'First Year' : y === '2' ? 'Second Year' : 'Third Year'
                        const monthName = MONTHS[(Number(mm) || 1) - 1] || ''
                        const day = (half === '1') ? '1' : '2'
                        return `${yearLabel} — ${monthName} ${day}`
                      })()
                const tentative = !!preset.plannedRacesTentative?.[r.dateKey]
                return (
                  <ListItemButton
                    key={`${r.dateKey}-${r.raceName}`}
                    onClick={() => remove(r.dateKey)}
                    sx={{ alignItems: 'center', gap: 1 }}
                  >
                    <Box
                      component="img"
                      src={banner}
                      alt=""
                      sx={{
                        width: 56,
                        height: 28,
                        objectFit: 'cover',
                        borderRadius: 0.5,
                        mr: 1,
                        display: 'block',
                        alignSelf: 'center',
                      }}
                    />
                    
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <span>{r.raceName}</span>
                          {badge && <Box component="img" src={badge} alt={r.instance.rank} sx={{ height: 18 }} />}
                          {tentative && <Chip size="small" label="Tentative" variant="outlined" />}
                        </Box>
                      }
                      secondary={`${prettyDate}${r.instance.location ? ` — ${r.instance.location}` : ''}${r.instance.distance_text ? ` — ${r.instance.distance_text}` : ''}`}
                    />
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0.5, minWidth: 56 }}>
                      <Tooltip title={tentative ? 'Unmark tentative' : 'Mark race as tentative'}>
                        <Switch
                          size="small"
                          checked={tentative}
                          onChange={(e) => {
                            e.stopPropagation()
                            toggleTentative(r.dateKey)
                          }}
                          onClick={(e) => e.stopPropagation()}
                        />
                      </Tooltip>
                      <Tooltip title="Remove race">
                        <IconButton edge="end" size="small" onClick={(e) => {
                          e.stopPropagation()
                          remove(r.dateKey)
                        }}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </ListItemButton>
                )
              })}
              {!selectedRows.length && (
                <Typography variant="caption" color="text.secondary">No planned races yet.</Typography>
              )}
            </List>
          </Paper>
        </Box>
      </Stack>
    </Paper>
  )
}
