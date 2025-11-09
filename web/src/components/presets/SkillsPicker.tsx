import React from 'react'
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  Stack,
  TextField,
  Typography,
  Paper,
  Chip,
  ToggleButton,
  ToggleButtonGroup,
  Avatar,
  Card,
  CardContent,
  CardHeader,
  useTheme,
} from '@mui/material'
import { styled } from '@mui/material/styles'

type GridProps = {
  container?: boolean
  spacing?: number
  xs?: number
  sm?: number
  lg?: number
  children?: React.ReactNode
}

const Grid = ({ container, spacing = 2, xs, sm, lg, children }: GridProps) => {
  if (container) {
    const StyledContainer = styled('div')(({ theme }) => ({
      display: 'flex',
      flexWrap: 'wrap',
      alignItems: 'stretch',
      margin: `-${theme.spacing(spacing)} 0 0 -${theme.spacing(spacing)}`,
      '& > *': {
        padding: `${theme.spacing(spacing)} 0 0 ${theme.spacing(spacing)}`,
        boxSizing: 'border-box',
      },
    }))
    return <StyledContainer>{children}</StyledContainer>
  }

  const StyledItem = styled('div')(({ theme }) => {
    const base = xs ? `${(xs / 12) * 100}%` : '100%'
    const styles: any = {
      flexBasis: base,
      maxWidth: base,
      boxSizing: 'border-box',
      display: 'flex',
    }
    if (sm) {
      styles[theme.breakpoints.up('sm')] = {
        flexBasis: `${(sm / 12) * 100}%`,
        maxWidth: `${(sm / 12) * 100}%`,
      }
    }
    if (lg) {
      styles[theme.breakpoints.up('lg')] = {
        flexBasis: `${(lg / 12) * 100}%`,
        maxWidth: `${(lg / 12) * 100}%`,
      }
    }
    return styles
  })

  return <StyledItem>{children}</StyledItem>
}
import SearchIcon from '@mui/icons-material/Search'
import SelectAllIcon from '@mui/icons-material/SelectAll'
import ClearAllIcon from '@mui/icons-material/ClearAll'
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline'
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutline'
import { useMemo, useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSkills } from '@/services/api'
import { useConfigStore } from '@/store/configStore'
import type { Skill, SkillRarity } from '@/models/datasets'

type CategoryMeta = {
  id: string
  label: string
  icon?: string
}

const rarityColors: Record<SkillRarity, string> = {
  normal: '#9e9e9e',
  gold: '#FFD54F',
  unique: 'linear-gradient(135deg,#8a2be2,#00e5ff,#ffd54f)',
}

const rarityBgColors: Record<SkillRarity, string> = {
  normal: '#9e9e9e15',
  gold: '#ffd54f33',
  unique: 'linear-gradient(135deg,#8a2be233,#00e5ff40,#ffd54f33)',
}

const FALLBACK_ICON = '/icons/skills/utx_ico_skill_9999.png'
const PAGE_SIZE = 21

const categoryOrder = [
  '1001', // buff
  '1002',
  '1003',
  '1004',
  '1005',
  '1006',
  '1007',
  '1008',
  '1009',
  '1010',
  '1011',
  '1012',
  '1013',
  '1014',
  '1015',
  '1016',
  '1017',
  '1018',
  '1019',
  '2001', // debuff
  '2002',
  '2003',
  '2004',
  '2005',
  '2006',
  '2007',
  '2008',
]


function getCategoryMeta(skills: Skill[]): CategoryMeta[] {
  const groups = new Map<string, { count: number; icon?: string }>()
  for (const skill of skills) {
    const category = skill.category ?? 'unknown'
    const icon = skill.icon_filename ? `/icons/skills/${skill.icon_filename}` : undefined
    const meta = groups.get(category)
    if (meta) {
      meta.count += 1
      if (!meta.icon && icon) meta.icon = icon
    } else {
      groups.set(category, { count: 1, icon })
    }
  }

  const order = (a: string, b: string) => {
    const ai = categoryOrder.indexOf(a)
    const bi = categoryOrder.indexOf(b)
    if (ai === -1 && bi === -1) return a.localeCompare(b)
    if (ai === -1) return 1
    if (bi === -1) return -1
    return ai - bi
  }

  const metas: CategoryMeta[] = []
  for (const [id, { icon }] of groups.entries()) {
    // Only show categories with actual icons beyond fallback
    if (icon && !icon.endsWith('utx_ico_skill_9999.png')) {
      metas.push({
        id,
        label: id === 'unknown' ? 'Misc' : id,
        icon,
      })
    }
  }
  metas.sort((a, b) => order(a.id, b.id))
  return metas
}

function rarityChip(_rarity: SkillRarity | undefined): React.ReactNode {
  // Don't show any badge for rarity
  return null
}

const rarityOptions: SkillRarity[] = ['normal', 'gold', 'unique']

export default function SkillsPicker({ presetId }: { presetId: string }) {
  const preset = useConfigStore((s) => s.getSelectedPreset().preset)
  const patchPreset = useConfigStore((s) => s.patchPreset)
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [rarityFilter, setRarityFilter] = useState<SkillRarity | 'all'>('all')
  const [page, setPage] = useState(0)
  const theme = useTheme()

  // Debounce search query with proper cleanup
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 400)
    return () => clearTimeout(timer)
  }, [q])

  // Reset pagination when filters change
  useEffect(() => {
    setPage(0)
  }, [debouncedQ, q, selectedCategories, rarityFilter])

  const { data: skills = [] } = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
  })

  if (!preset) return null

  const selected = new Set(preset.skillsToBuy)

  const categories = useMemo(() => getCategoryMeta(skills), [skills])

  const filtered = useMemo<Skill[]>(() => {
    const rawTerm = q.trim().toLowerCase()
    if (rawTerm.length > 0 && rawTerm.length < 3) {
      return []
    }

    const term = debouncedQ.trim().toLowerCase()

    return skills.filter((s) => {
      const matchesQuery = !term
        || s.name.toLowerCase().includes(term)
        || (s.description || '').toLowerCase().includes(term)

      const matchesCategory = !selectedCategories.length
        || selectedCategories.includes(s.category ?? 'unknown')

      const matchesRarity = rarityFilter === 'all'
        || (s.rarity ?? 'normal') === rarityFilter

      return matchesQuery && matchesCategory && matchesRarity
    })
  }, [skills, debouncedQ, selectedCategories, rarityFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))

  useEffect(() => {
    if (page >= totalPages) {
      setPage(totalPages - 1)
    }
  }, [page, totalPages])

  const paginated = useMemo(() => {
    const start = page * PAGE_SIZE
    return filtered.slice(start, start + PAGE_SIZE)
  }, [filtered, page])

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
      <Box sx={{ mt: 1, display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
        {preset.skillsToBuy.map(n => {
          const skill = skills.find(s => s.name === n)
          const icon = skill?.icon_filename ? `/icons/skills/${skill.icon_filename}` : FALLBACK_ICON
          const chipStyle = skill?.rarity === 'unique'
            ? {
                background: rarityBgColors.unique,
                color: theme.palette.text.primary,
                '& .MuiChip-deleteIcon': {
                  color: theme.palette.text.secondary,
                },
              }
            : {
                bgcolor: skill?.rarity ? rarityBgColors[skill.rarity] : 'background.paper',
              }
          return (
            <Chip
              key={n}
              avatar={<Avatar src={icon} variant="rounded" sx={{ width: 28, height: 28 }} />}
              label={n}
              size="small"
              onDelete={() => remove(n)}
              sx={{
                ...chipStyle,
                maxWidth: 200,
              }}
            />
          )
        })}
        {!preset.skillsToBuy.length && (
          <Typography variant="caption" color="text.secondary">No skills selected.</Typography>
        )}
      </Box>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth>
        <DialogTitle>Skill Library</DialogTitle>
        <DialogContent sx={{ p: 0 }}>
          <Stack direction="row" spacing={0} sx={{ height: 'calc(100vh - 200px)', minHeight: 500 }}>
            {/* Left: Search, filters, grid */}
            <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', p: 2, pr: 1 }}>
              <Stack spacing={2}>
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={2}
                  alignItems={{ xs: 'stretch', md: 'center' }}
                >
                  <TextField
                    fullWidth
                    size="small"
                    placeholder="Search by name or description (min 3 characters)"
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <SearchIcon fontSize="small" />
                        </InputAdornment>
                      ),
                    }}
                    helperText={q.length > 0 && q.length < 3 ? `Type ${3 - q.length} more character${3 - q.length > 1 ? 's' : ''} to search` : ''}
                  />
                  <ToggleButtonGroup
                    value={rarityFilter}
                    exclusive
                    onChange={(_, val) => val && setRarityFilter(val)}
                    size="small"
                    color="primary"
                  >
                    <ToggleButton value="all">ALL</ToggleButton>
                    {rarityOptions.map((r) => (
                      <ToggleButton
                        key={r}
                        value={r}
                        sx={{
                          bgcolor: rarityFilter === r ? `${rarityColors[r]}30` : undefined,
                          '&.Mui-selected': {
                            bgcolor: `${rarityColors[r]}40`,
                            color: rarityColors[r],
                          },
                        }}
                      >
                        {r.toUpperCase()}
                      </ToggleButton>
                    ))}
                  </ToggleButtonGroup>
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Chip
                    icon={<SelectAllIcon fontSize="small" />}
                    label="All types"
                    size="small"
                    color={!selectedCategories.length ? 'primary' : 'default'}
                    onClick={() => setSelectedCategories([])}
                  />
                  {categories.map((cat) => (
                    <Box
                      key={cat.id}
                      onClick={() => {
                        setSelectedCategories((prev) =>
                          prev.includes(cat.id)
                            ? prev.filter((id) => id !== cat.id)
                            : [...prev, cat.id]
                        )
                      }}
                      sx={{
                        width: 48,
                        height: 48,
                        borderRadius: 2,
                        border: '2px solid',
                        borderColor: selectedCategories.includes(cat.id) 
                          ? theme.palette.primary.main 
                          : theme.palette.divider,
                        bgcolor: selectedCategories.includes(cat.id)
                          ? `${theme.palette.primary.main}15`
                          : 'background.paper',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        p: 0.5,
                        transition: 'all 0.2s',
                        '&:hover': {
                          borderColor: theme.palette.primary.main,
                          bgcolor: `${theme.palette.primary.main}08`,
                        },
                      }}
                    >
                      <Box
                        component="img"
                        src={cat.icon}
                        sx={{
                          width: '100%',
                          height: '100%',
                          objectFit: 'contain',
                        }}
                      />
                    </Box>
                  ))}
                  {!!selectedCategories.length && (
                    <Box
                      sx={{
                        display: 'flex',
                        justifyContent: 'center',
                        alignItems: 'center',
                        mt: 2,
                        mb: 1,
                      }}
                    >
                      <Button
                        variant="contained"
                        color="error"
                        startIcon={<ClearAllIcon fontSize="small" />}
                        onClick={() => setSelectedCategories([])}
                      >
                        Clear
                      </Button>
                    </Box>
                  )}
                </Stack>
              </Stack>

              <Box sx={{ flex: 1, overflow: 'auto', mt: 2 }}>
                {q.length > 0 && q.length < 3 ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', p: 4 }}>
                    <Typography variant="body2" color="text.secondary" align="center">
                      Type at least 3 characters to start searching
                    </Typography>
                  </Box>
                ) : filtered.length === 0 ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', p: 4 }}>
                    <Typography variant="body2" color="text.secondary" align="center">
                      No skills found
                    </Typography>
                  </Box>
                ) : (
                  <Grid container spacing={1.5}>
                    {paginated.map((skill) => {
                    const icon = skill.icon_filename ? `/icons/skills/${skill.icon_filename}` : FALLBACK_ICON
                    const selectedState = selected.has(skill.name)
                    const toggleSkill = () => {
                      selectedState ? remove(skill.name) : add(skill.name)
                    }
                    return (
                      <Grid key={skill.name} xs={12} sm={6} lg={4}>
                        <Card
                          variant="outlined"
                          sx={{
                            borderColor: selectedState ? theme.palette.primary.main : 'divider',
                            bgcolor: selectedState
                              ? `${theme.palette.primary.main}08`
                              : skill.rarity
                              ? rarityBgColors[skill.rarity]
                              : 'background.paper',
                            background: skill.rarity === 'unique'
                              ? 'linear-gradient(135deg, rgba(138,43,226,0.15), rgba(0,229,255,0.15), rgba(255,213,79,0.15))'
                              : undefined,
                            position: 'relative',
                            height: '100%',
                            display: 'flex',
                            flexDirection: 'column',
                            width: '100%',
                            cursor: 'pointer',
                            '&:hover': {
                              borderColor: theme.palette.primary.main,
                              bgcolor: selectedState
                                ? `${theme.palette.primary.main}12`
                                : `${theme.palette.primary.main}0A`,
                            },
                          }}
                          onClick={toggleSkill}
                        >
                          <CardHeader
                            avatar={<Avatar src={icon} variant="rounded" sx={{ width: 32, height: 32 }} />}
                            title={
                              <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="space-between">
                                <Stack direction="row" spacing={0.5} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
                                  <Typography variant="body2" noWrap sx={{ flex: 1 }}>{skill.name}</Typography>
                                  {rarityChip(skill.rarity)}
                                </Stack>
                                <IconButton
                                  size="small"
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    toggleSkill()
                                  }}
                                  color={selectedState ? 'error' : 'primary'}
                                >
                                  {selectedState ? <RemoveCircleOutlineIcon fontSize="small" /> : <AddCircleOutlineIcon fontSize="small" />}
                                </IconButton>
                              </Stack>
                            }
                            sx={{ pb: 0.5 }}
                          />
                          <CardContent sx={{ pt: 0, pb: 1, '&:last-child': { pb: 1 }, flexGrow: 1 }}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical',
                                overflow: 'hidden',
                                lineHeight: 1.4,
                              }}
                            >
                              {skill.description || 'No description'}
                            </Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    )
                  })}
                </Grid>
                )}
              </Box>

              {filtered.length > PAGE_SIZE && (
                <Stack direction="row" spacing={1} justifyContent="center" alignItems="center" sx={{ mt: 2 }}>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setPage((prev) => Math.max(0, prev - 1))}
                    disabled={page === 0}
                  >
                    Previous
                  </Button>
                  <Typography variant="caption" color="text.secondary">
                    Page {page + 1} of {totalPages}
                  </Typography>
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => setPage((prev) => Math.min(totalPages - 1, prev + 1))}
                    disabled={page >= totalPages - 1}
                  >
                    Next
                  </Button>
                </Stack>
              )}
            </Box>

            {/* Right: Selected sidebar */}
            <Box
              sx={{
                width: 320,
                borderLeft: 1,
                borderColor: 'divider',
                display: 'flex',
                flexDirection: 'column',
                bgcolor: 'background.default',
              }}
            >
              <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
                <Typography variant="subtitle2">
                  Selected ({preset.skillsToBuy.length})
                </Typography>
              </Box>
              <List dense sx={{ flex: 1, overflow: 'auto', p: 0 }}>
                {preset.skillsToBuy.map((name) => {
                  const skill = skills.find((s) => s.name === name)
                  const icon = skill?.icon_filename ? `/icons/skills/${skill.icon_filename}` : FALLBACK_ICON
                  return (
                    <ListItem
                      key={name}
                      sx={{
                        borderBottom: 1,
                        borderColor: 'divider',
                        '&:hover': { bgcolor: 'action.hover' },
                      }}
                      secondaryAction={
                        <IconButton edge="end" size="small" onClick={() => remove(name)} color="error">
                          <RemoveCircleOutlineIcon fontSize="small" />
                        </IconButton>
                      }
                    >
                      <ListItemText
                        primary={
                          <Stack direction="row" spacing={1} alignItems="center">
                            <Avatar src={icon} variant="rounded" sx={{ width: 40, height: 40 }} />
                            <Typography variant="body2" noWrap sx={{ flex: 1, pr: 1 }}>{name}</Typography>
                          </Stack>
                        }
                        secondary={
                          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                            {skill?.description}
                          </Typography>
                        }
                      />
                    </ListItem>
                  )
                })}
                {!preset.skillsToBuy.length && (
                  <Typography variant="caption" color="text.secondary" sx={{ p: 2, display: 'block', textAlign: 'center' }}>
                    No skills selected yet.
                  </Typography>
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
