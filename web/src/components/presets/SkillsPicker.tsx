import {
  Box, Button, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, InputAdornment, List, ListItem, ListItemButton, ListItemText,
  Stack, TextField, Typography, Paper, Chip,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import DeleteIcon from '@mui/icons-material/Delete'
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSkills } from '@/services/api'
import { useConfigStore } from '@/store/configStore'
import type { Skill } from '@/models/datasets'

export default function SkillsPicker({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.config.presets.find((p) => p.id === presetId))
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')

  const { data: skills = [] } = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
  })

  if (!preset) return null

  const selected = new Set(preset.skillsToBuy)
  const filtered = useMemo<Skill[]>(
    () => skills.filter(s =>
      s.name.toLowerCase().includes(q.toLowerCase()) ||
      (s.description || '').toLowerCase().includes(q.toLowerCase())
    ),
    [skills, q],
  )

  const add = (name: string) => {
    if (selected.has(name)) return
    patchPreset(presetId, 'skillsToBuy', [...preset.skillsToBuy, name])
  }
  const remove = (name: string) => {
    patchPreset(presetId, 'skillsToBuy', preset.skillsToBuy.filter(n => n !== name))
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between">
        <Typography variant="subtitle2">Skills to buy</Typography>
        <Button size="small" variant="outlined" onClick={() => setOpen(true)}>
          Open picker
        </Button>
      </Stack>

      {/* quick preview */}
      <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        {preset.skillsToBuy.map(n => (
          <Chip key={n} label={n} onDelete={() => remove(n)} />
        ))}
        {!preset.skillsToBuy.length && (
          <Typography variant="caption" color="text.secondary">No skills selected.</Typography>
        )}
      </Box>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Skills List</DialogTitle>
        <DialogContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mt: 1 }}>
            {/* Left: search + results */}
            <Box sx={{ flex: 1, minWidth: 280 }}>
              <TextField
                fullWidth size="small" placeholder="Search..."
                value={q} onChange={(e) => setQ(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start"><SearchIcon /></InputAdornment>
                  ),
                }}
              />
              <List dense sx={{ maxHeight: 420, overflow: 'auto', mt: 1 }}>
                {filtered.map((s) => (
                  <ListItem key={s.name} disableGutters>
                    <ListItemButton onClick={() => add(s.name)}>
                      <ListItemText
                        primary={s.name}
                        secondary={s.description}
                        secondaryTypographyProps={{ noWrap: true }}
                      />
                    </ListItemButton>
                  </ListItem>
                ))}
                {!filtered.length && (
                  <Typography variant="caption" color="text.secondary">
                    No results. Is /api/skills available?
                  </Typography>
                )}
              </List>
            </Box>

            {/* Right: selected */}
            <Box sx={{ flex: 1, minWidth: 280 }}>
              <Typography variant="subtitle2">Selected</Typography>
              <List dense sx={{ maxHeight: 420, overflow: 'auto', mt: 1 }}>
                {preset.skillsToBuy.map((n) => (
                  <ListItem
                    key={n}
                    secondaryAction={
                      <IconButton edge="end" onClick={() => remove(n)}><DeleteIcon /></IconButton>
                    }
                  >
                    <ListItemText primary={n} />
                  </ListItem>
                ))}
                {!preset.skillsToBuy.length && (
                  <Typography variant="caption" color="text.secondary">Nothing selected.</Typography>
                )}
              </List>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  )
}
