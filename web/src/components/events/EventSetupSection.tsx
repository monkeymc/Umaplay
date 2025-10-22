import { useMemo, useState } from 'react'
import {
  Box, Card, CardActionArea, CardContent, Chip, Dialog, DialogContent, DialogTitle,
  Divider, IconButton, InputAdornment, Stack, TextField, Tooltip, Typography
} from '@mui/material'
import EditIcon from '@mui/icons-material/Tune'
import CloseIcon from '@mui/icons-material/Close'
import SearchIcon from '@mui/icons-material/Search'
import PriorityHighIcon from '@mui/icons-material/PriorityHigh'
import type {
  EventsIndex,
  SupportSet,
  ScenarioSet,
  TraineeSet,
  AttrKey,
  EventOptionEffect,
  ChoiceEvent,
} from '@/types/events'
import SmartImage from '@/components/common/SmartImage'
import { supportImageCandidates, scenarioImageCandidates, traineeImageCandidates, supportTypeIcons } from '@/utils/imagePaths'
import { useEventsSetupStore } from '@/store/eventsSetupStore'
import { pickFor } from '@/utils/eventPick'
import SupportPriorityDialog from './SupportPriorityDialog'

type Props = { index: EventsIndex }

// ---- helpers
const ATTR_ORDER: AttrKey[] = ['SPD','STA','PWR','GUTS','WIT','PAL']

// --- visuals
const THUMB = 64
const THUMB_H = 86
const rarityFrameSx = (rarity: string, w?: number, h?: number) => {
  const base = {
    position: 'relative' as const,
    borderRadius: 1,
    p: '2px',
    display: 'inline-block',
    lineHeight: 0,
    // Enforce a fixed box; image will fill it uniformly
    width: w,
    height: h,
    '& img': {
      width: '100%',
      height: '100%',
      objectFit: 'cover',
      imageRendering: 'auto',
      borderRadius: 1,
      display: 'block',
    },
  }
  if (rarity === 'SSR') {
    return { ...base, background: 'linear-gradient(135deg,#8a2be2,#00e5ff,#ffd54f)' }
  }
  if (rarity === 'SR') {
    return { ...base, background: 'linear-gradient(135deg,#d4af37,#fff4c2)' }
  }
  // R or fallback
  return { ...base, background: 'linear-gradient(135deg,#cfd8dc,#eceff1)' }
}

const emptySlotSx = {
  width: THUMB,
  height: THUMB_H,
  borderRadius: 1,
  display: 'grid',
  placeItems: 'center',
  bgcolor: 'action.hover',
  border: '1px dashed',
  borderColor: 'divider',
} as const

// sorting: SSR first, then SR, then R; tie-break by name
const rarityRank = (r: string) =>
  r === 'SSR' ? 0 : r === 'SR' ? 1 : r === 'R' ? 2 : 9


// ---- Support picker dialog
function SupportPickerDialog({
  open, onClose, index, onPick,
}: { open: boolean; onClose: () => void; index: EventsIndex; onPick: (s: SupportSet) => void }) {
  const [query, setQuery] = useState('')
  const [attrFilter, setAttrFilter] = useState<AttrKey>('SPD')
  // Build both: per-attribute lists AND a global 'all' list for queries.
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const byAttrOut: Record<AttrKey, SupportSet[]> = {
      SPD: [], STA: [], PWR: [], GUTS: [], WIT: [], PAL: [], None: [],
    }
    let all: SupportSet[] = []

    const byAttr = index.supports as any // Map<AttrKey, Map<Rarity, SupportSet[]>>
    if (byAttr instanceof Map) {
      for (const attr of ATTR_ORDER) {
        const rarMap = byAttr.get(attr)
        let list: SupportSet[] = []
        if (rarMap instanceof Map) {
          for (const arr of rarMap.values()) list = list.concat(arr as SupportSet[])
          // sort SSR → SR → R, then by name
          list.sort((a, b) => {
            const ra = rarityRank(String(a.rarity))
            const rb = rarityRank(String(b.rarity))
            if (ra !== rb) return ra - rb
            return a.name.localeCompare(b.name)
          })
        }
        const filt = q ? list.filter(s => s.name.toLowerCase().includes(q)) : list
        byAttrOut[attr] = filt
        if (q) all = all.concat(filt)
      }
    }
    if (q) {
      // keep global list nicely sorted as well
      all.sort((a, b) => {
        const ra = rarityRank(String(a.rarity))
        const rb = rarityRank(String(b.rarity))
        if (ra !== rb) return ra - rb
        return a.name.localeCompare(b.name)
      })
    }
    return { byAttr: byAttrOut, all }
  }, [index, query])
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display:'flex', alignItems:'center', gap:1 }}>
        Select Support
        <Box flex={1} />
        <IconButton onClick={onClose}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          fullWidth
          size="small"
          placeholder="Search supports…"
          value={query}
          onChange={e => setQuery(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }}
          sx={{ mb: 2 }}
        />
        {/* Attribute filter buttons */}
        <Stack direction="row" spacing={1} sx={{ mb: 1, flexWrap: 'wrap' }}>
          {ATTR_ORDER.map((a) => (
            <Box
              key={a}
              role="button"
              onClick={() => setAttrFilter(a)}
              sx={{
                display: 'flex', alignItems: 'center', gap: 0.75,
                px: 1, py: 0.5, borderRadius: 1, cursor: 'pointer',
                bgcolor: attrFilter === a ? 'action.selected' : 'action.hover',
                border: '1px solid',
                borderColor: attrFilter === a ? 'primary.main' : 'divider',
                userSelect: 'none',
              }}
            >
              <img src={supportTypeIcons[a]} width={18} height={18} />
              <Typography variant="caption">{a}</Typography>
            </Box>
          ))}
        </Stack>
        <Divider sx={{ mb: 2 }} />
        {/* Visible list for the selected attribute */}
        <Stack direction="row" flexWrap="wrap" gap={1.5}>
          {((query.trim()
              ? filtered.all
              : filtered.byAttr[attrFilter]) || []
            ).map((s) => (
            <Box
              key={`${s.name}-${s.rarity}-${s.attribute}`}
              sx={{ flexBasis: { xs: 'calc(50% - 12px)', sm: 'calc(33.33% - 12px)', md: 'calc(25% - 12px)' } }}
            >
              <Card variant="outlined">
                <CardActionArea onClick={() => onPick(s)}>
                  <Stack direction="row" spacing={1} sx={{ p: 1, alignItems:'center' }}>
                    {/* force high-quality scaling for the inner <img> regardless of global styles */}
                    <Box sx={rarityFrameSx(String(s.rarity), 48, 64)}>
                      <SmartImage
                        candidates={supportImageCandidates(s.name, s.rarity, s.attribute)}
                        alt={s.name}
                        width={48}
                        height={64}
                        rounded={6}
                      />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" noWrap>{s.name}</Typography>
                      {/* rarity text removed per design; keep attribute subtle if you want */}
                    </Box>
                  </Stack>
                </CardActionArea>
              </Card>
            </Box>
          ))}
        </Stack>
      </DialogContent>
    </Dialog>
  )
}

// ---- Scenario picker
function ScenarioPickerDialog({
  open, onClose, scenarios, onPick,
}: { open: boolean; onClose: () => void; scenarios: ScenarioSet[]; onPick: (s: ScenarioSet) => void }) {
  const [q, setQ] = useState('')
  const list = useMemo(() => q ? scenarios.filter(s => s.name.toLowerCase().includes(q.toLowerCase())) : scenarios, [q, scenarios])
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display:'flex', alignItems:'center' }}>
        Select Scenario
        <Box flex={1} />
        <IconButton onClick={onClose}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          fullWidth size="small" placeholder="Search scenario…"
          value={q} onChange={e => setQ(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }}
          sx={{ mb: 2 }}
        />
        <Stack direction="row" flexWrap="wrap" gap={1.5}>
          {list.map(s => (
            <Box key={s.name} sx={{ flexBasis: { xs: 'calc(50% - 12px)', sm: 'calc(33.33% - 12px)' } }}>
              <Card variant="outlined">
                <CardActionArea onClick={() => onPick(s)}>
                  <Stack direction="row" spacing={1} sx={{ p: 1, alignItems: 'center' }}>
                    <SmartImage candidates={scenarioImageCandidates(s.name)} alt={s.name} width={48} height={48} rounded={6}/>
                    <Typography variant="body2" noWrap>{s.name}</Typography>
                  </Stack>
                </CardActionArea>
              </Card>
            </Box>
          ))}
        </Stack>
      </DialogContent>
    </Dialog>
  )
}

// ---- Trainee picker
function TraineePickerDialog({
  open, onClose, trainees, onPick,
}: { open: boolean; onClose: () => void; trainees: TraineeSet[]; onPick: (t: TraineeSet) => void }) {
  const [q, setQ] = useState('')
  const list = useMemo(() => q ? trainees.filter(t => t.name.toLowerCase().includes(q.toLowerCase())) : trainees, [q, trainees])
  
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display:'flex', alignItems:'center' }}>
        Select Trainee
        <Box flex={1} />
        <IconButton onClick={onClose}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        <TextField
          fullWidth size="small" placeholder="Search trainee…"
          value={q} onChange={e => setQ(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }}
          sx={{ mb: 2 }}
        />
        <Stack direction="row" flexWrap="wrap" gap={1.5}>
          {list.map(t => (
            <Box key={t.name} sx={{ flexBasis: { xs: 'calc(50% - 12px)', sm: 'calc(33.33% - 12px)', md: 'calc(25% - 12px)' } }}>
              <Card variant="outlined">
                <CardActionArea onClick={() => onPick(t)}>
                  <Stack direction="row" spacing={1} sx={{ p: 1, alignItems: 'center' }}>
                    <SmartImage candidates={traineeImageCandidates(t.name)} alt={t.name} width={48} height={48} rounded={6}/>
                    <Typography variant="body2" noWrap>{t.name}</Typography>
                  </Stack>
                </CardActionArea>
              </Card>
            </Box>
          ))}
        </Stack>
      </DialogContent>
    </Dialog>
  )
}

// ---- Per-card event options dialog (override picker)
function EventOptionsDialog({
  open, onClose, title, items,
  type, // determines fallback pick
  onPick,
}: {
  open: boolean
  onClose: () => void
  title: string
  items: {
    key: string
    keyStep: string
    evType?: string
    eventName: string
    chainStep: number
    defaultPref?: number
    // richer options: label + raw outcomes so we can show details
    options: { label: string; num: number; outcomes: EventOptionEffect[] }[]
  }[]
  type: 'support'|'scenario'|'trainee'
  onPick: (keyStep: string, pick: number) => void
}) {
  const prefs = useEventsSetupStore((s) => s.setup.prefs)
  const [q, setQ] = useState('')

  // helpers to render compact effect chips
  const fmtSigned = (n: number) => (n > 0 ? `+${n}` : `${n}`)
  const effectChips = (obj: Record<string, any>) => {
    const chips: string[] = []
    // common keys we know about
    if (typeof obj.energy === 'number') chips.push(`Energy ${fmtSigned(obj.energy)}`)
    if (typeof obj.energy_max === 'number') chips.push(`Max Energy ${fmtSigned(obj.energy_max)}`)
    if (typeof obj.skill_pts === 'number') chips.push(`Skill Pts ${fmtSigned(obj.skill_pts)}`)
    if (typeof obj.bond === 'number') chips.push(`Bond ${fmtSigned(obj.bond)}`)
    if (typeof obj.mood === 'number') chips.push(`Mood ${fmtSigned(obj.mood)}`)
    if (typeof obj.speed === 'number') chips.push(`SPD ${fmtSigned(obj.speed)}`)
    if (typeof obj.stamina === 'number') chips.push(`STA ${fmtSigned(obj.stamina)}`)
    if (typeof obj.power === 'number') chips.push(`PWR ${fmtSigned(obj.power)}`)
    if (typeof obj.guts === 'number') chips.push(`GUTS ${fmtSigned(obj.guts)}`)
    if (typeof obj.wit === 'number') chips.push(`WIT ${fmtSigned(obj.wit)}`)
    if (typeof obj.stats === 'number') chips.push(`All stats ${fmtSigned(obj.stats)}`)
    if (obj.status) chips.push(`Status: ${String(obj.status)}`)
    if (Array.isArray(obj.hints) && obj.hints.length) chips.push(`Hints: ${obj.hints.slice(0,3).join(', ')}${obj.hints.length>3?'…':''}`)
    if (typeof obj.random_chance === 'number') chips.push(`${obj.random_chance}%`)
    return chips
  }

  const filtered = useMemo(
    () => (q.trim()
      ? items.filter(it => it.eventName.toLowerCase().includes(q.trim().toLowerCase()))
      : items),
    [items, q]
  )
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle sx={{ display:'flex', alignItems:'center' }}>
        {title}
        <Box flex={1} />
        <IconButton onClick={onClose}><CloseIcon /></IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {/* search events */}
        <TextField
          fullWidth size="small" placeholder="Search events…"
          value={q} onChange={e => setQ(e.target.value)}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon /></InputAdornment> }}
          sx={{ mb: 2 }}
        />
        <Stack spacing={1.25}>
          {filtered.map(it => {
            const defaultPick = pickFor(prefs, it.keyStep, it.key, it.defaultPref, type)
            return (
              <Card variant="outlined" key={it.keyStep}>
                <CardContent sx={{ p: 1.25 }}>
                  {/* Header */}
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <Box sx={{ px: 0.75, py: 0.25, borderRadius: 1, bgcolor: 'secondary.light', color: 'secondary.contrastText', fontSize: 11 }}>
                      Chain step: {it.chainStep}
                    </Box>
                    {!!it.evType && (
                      <Box sx={{ px: 0.75, py: 0.25, borderRadius: 1, bgcolor: it.evType === 'chain' ? 'warning.light' : it.evType === 'random' ? 'info.light' : 'action.hover', fontSize: 11 }}>
                        {it.evType}
                      </Box>
                    )}
                    <Typography variant="subtitle1" sx={{ flex: 1, ml: !!it.evType ? 0.5 : 0, fontWeight: 700 }}>
                      {it.eventName}
                    </Typography>
                  </Stack>
                  {/* Options */}
                  <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
                    {it.options.map((opt) => {
                      const active = defaultPick === opt.num
                      const isRandom = Array.isArray(opt.outcomes) && opt.outcomes.length > 1
                      return (
                        <Box
                          key={opt.num}
                          role="button"
                          onClick={() => onPick(it.keyStep, opt.num)}
                          sx={{
                            borderRadius: 1,
                            border: '1px solid',
                            borderColor: active ? 'primary.main' : 'divider',
                            px: 1, py: 0.75,
                            fontSize: 12,
                            cursor: 'pointer',
                            userSelect: 'none',
                            minWidth: 140,
                            bgcolor: active ? 'primary.lerp?0.95' as any : 'background.paper',
                          }}
                        >
                         <Stack spacing={0.5}>
                            <Typography variant="caption" sx={{ fontWeight: 700 }}>
                              {opt.num}. {opt.label}{isRandom ? ' (random, either A or B)' : ''}
                            </Typography>
                            {/* Single outcome → one compact chip row */}
                            {!isRandom && !!opt.outcomes?.length && (
                              <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                                {effectChips(opt.outcomes[0]).map((c, i) => (
                                  <Box key={i} sx={{ px: 0.5, py: 0.25, borderRadius: 1, bgcolor: 'action.hover' }}>{c}</Box>
                                ))}
                              </Stack>
                            )}
                            {/* Random outcomes → labelled list A/B/C… */}
                            {isRandom && (
                              <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                                {opt.outcomes.map((o, i) => (
                                  <Stack key={i} direction="row" spacing={0.75} alignItems="flex-start" sx={{ flexWrap: 'wrap' }}>
                                    <Box sx={{ px: 0.5, py: 0.05, borderRadius: 0.5, bgcolor: 'black', color: 'white', fontSize: 11, minWidth: 14, textAlign: 'center' }}>
                                      {String.fromCharCode(65 + i)}
                                    </Box>
                                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                                      {effectChips(o).map((c, j) => (
                                        <Box key={j} sx={{ px: 0.5, py: 0.25, borderRadius: 1, bgcolor: 'action.hover' }}>{c}</Box>
                                      ))}
                                    </Stack>
                                  </Stack>
                                ))}
                              </Stack>
                            )}
                          </Stack>
                        </Box>
                      )
                    })}
                  </Stack>
                </CardContent>
              </Card>
            )
          })}
        </Stack>
      </DialogContent>
    </Dialog>
  )
}

// ---- main section
export default function EventSetupSection({ index }: Props) {
  const supports    = useEventsSetupStore((s) => s.setup.supports)
  const scenario    = useEventsSetupStore((s) => s.setup.scenario)
  const trainee     = useEventsSetupStore((s) => s.setup.trainee)
  const setSupport  = useEventsSetupStore((s) => s.setSupport)
  const setScenario = useEventsSetupStore((s) => s.setScenario)
  const setTrainee  = useEventsSetupStore((s) => s.setTrainee)
  const setOverride = useEventsSetupStore((s) => s.setOverride)

  // dialogs state
  const [pickSlot, setPickSlot] = useState<number | null>(null)
  const [scenarioOpen, setScenarioOpen] = useState(false)
  const [traineeOpen, setTraineeOpen] = useState(false)
  const [optionsFor, setOptionsFor] = useState<{ type:'support'|'scenario'|'trainee'; title: string; items: any[] } | null>(null)
  const [prioritySlot, setPrioritySlot] = useState<number | null>(null)

  const openOptionsForSupport = (slot: number) => {
    const sel = supports[slot]
    if (!sel) return
    // Runtime: index.supports is Map<AttrKey, Map<Rarity, SupportSet[]>>
    let set: SupportSet | undefined
    const byAttr = index.supports as any
    console.log("DEBUG openOptionsForSupport index.supports", index.supports)
    if (byAttr instanceof Map) {
      const rarMap = byAttr.get(sel.attribute)
      if (rarMap instanceof Map) {
        const exactArr = rarMap.get(sel.rarity) as SupportSet[] | undefined
        set = exactArr?.find(s => s.name === sel.name)
        if (!set) {
          for (const arr of rarMap.values()) {
            const found = (arr as SupportSet[]).find(s => s.name === sel.name)
            if (found) { set = found; break }
          }
        }
      }
    }
    if (!set) return
    
    const evs: ChoiceEvent[] = (((set as unknown as { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] }).events)
      ?? ((set as unknown as { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] }).choice_events)
      ?? [])
    const items = evs.map((ev: any) => ({
      key: `support/${set.name}/${set.attribute}/${set.rarity}/${ev.name}`,
      keyStep: `support/${set.name}/${set.attribute}/${set.rarity}/${ev.name}#s${ev.chain_step ?? 1}`,
      evType: ev.type,
      eventName: ev.name,
      chainStep: ev.chain_step ?? 1,
      defaultPref: ev.default_preference,
      options: (Object.entries(ev.options || {}) as [string, EventOptionEffect[]][])
        .map(([k, arr]) => ({
        label: `Option ${k}`,
        num: Number(k),
        outcomes: Array.isArray(arr) ? arr : [],
      })),
    }))

    setOptionsFor({ type: 'support', title: `${set.name} — events`, items })
  }

  const openOptionsForScenario = () => {
    if (!scenario) return
    const set = index.scenarios.find(s => s.name === scenario.name)
    if (!set) return
    const evs: ChoiceEvent[] = (((set as unknown as { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] }).events)
      ?? ((set as unknown as { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] }).choice_events)
      ?? [])
    const items = evs.map((ev: any) => ({
      key: `scenario/${set.name}/None/None/${ev.name}`,
      keyStep: `scenario/${set.name}/None/None/${ev.name}#s${ev.chain_step ?? 1}`,
      evType: ev.type,
      eventName: ev.name,
      chainStep: ev.chain_step ?? 1,
      defaultPref: ev.default_preference,
      options: (Object.entries(ev.options || {}) as [string, EventOptionEffect[]][])
        .map(([k, arr]) => ({
        label: `Option ${k}`,
        num: Number(k),
        outcomes: Array.isArray(arr) ? arr : [],
      })),
    }))
    setOptionsFor({ type: 'scenario', title: `${set.name} — events`, items })
  }

  const openOptionsForTrainee = () => {
    if (!trainee) return

    const general = (index.trainees as any)?.general as { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] } | null | undefined
    const specMap = (index.trainees as any)?.specific as Map<string, { events?: ChoiceEvent[]; choice_events?: ChoiceEvent[] }> | undefined
    const specific = specMap?.get(trainee.name) ?? null

    const genEvents: ChoiceEvent[] =
      (general?.events ?? general?.choice_events ?? []) as ChoiceEvent[]
    const specEvents: ChoiceEvent[] =
      (specific?.events ?? specific?.choice_events ?? []) as ChoiceEvent[]

    // ---- Merge with override:
    // When a specific trainee has an event with the same (name, chain_step),
    // it REPLACES the general one. Otherwise, general events are kept.
    const norm = (s: string) => s.trim().replace(/\s+/g, ' ').toLowerCase()
    const evKey = (ev: ChoiceEvent) => `${norm(ev.name)}#${Number(ev.chain_step ?? 1)}`
    const specKeys = new Set(specEvents.map(evKey))
    // Put specific events first (their own order), then remaining general ones
    const merged: ChoiceEvent[] = [
      ...specEvents,
      ...genEvents.filter((e) => !specKeys.has(evKey(e))),
    ]

    const owner = specific ? specific as any : { name: 'general' }
    const items = merged.map((ev) => ({
      key: `trainee/${owner.name}/None/None/${ev.name}`,
      keyStep: `trainee/${owner.name}/None/None/${ev.name}#s${ev.chain_step ?? 1}`,
      evType: ev.type,
      eventName: ev.name,
      chainStep: ev.chain_step ?? 1,
      defaultPref: ev.default_preference,
      options: (Object.entries(ev.options || {}) as [string, EventOptionEffect[]][])
        .map(([k, arr]) => ({
        label: `Option ${k}`,
        num: Number(k),
        outcomes: Array.isArray(arr) ? arr : [],
      })),
    }))
    setOptionsFor({ type: 'trainee', title: `${trainee.name} — events`, items })
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h6">Event Setup</Typography>

      {/* Supports */}
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="subtitle1">Support Deck (up to 6)</Typography>
          </Stack>
          <Stack direction="row" flexWrap="wrap" gap={1.5}>
            {supports.map((sel, idx) => (
              <Box key={idx} sx={{ flexBasis: { xs: 'calc(50% - 12px)', sm: 'calc(33.33% - 12px)', md: 'calc(16.66% - 12px)' } }}>
                <Card variant="outlined" sx={{ position:'relative' }}>
                  <CardActionArea onClick={() => setPickSlot(idx)}>
                    <Stack alignItems="center" spacing={1} sx={{ p: 1 }}>
                      {sel ? (
                        <>
                          <Box sx={rarityFrameSx(sel.rarity || '', THUMB, THUMB_H)}>
                            <SmartImage
                              candidates={supportImageCandidates(sel.name || "", sel.rarity, sel.attribute)}
                              alt={sel.name || ""}
                              width={THUMB}
                              height={THUMB_H}
                              rounded={8}
                            />
                            {/* attribute icon overlay */}
                            <Box sx={{
                              position:'absolute', top:0, left:0, p:'0px',
                              border: '1px solid', borderColor: 'divider',
                            }}>
                              <img src={supportTypeIcons[sel.attribute || ""]} width={16} height={16} />
                            </Box>
                          </Box>
                          <Typography variant="body2" noWrap>{sel.name}</Typography>
                          {(() => {
                            const pr = sel.priority
                            const hasCustom = pr
                              ? (!pr.enabled || pr.scoreBlueGreen !== 0.75 || pr.scoreOrangeMax !== 0.5)
                              : false
                            if (!pr) return null
                            return (
                              <Stack spacing={0.5} alignItems="center" sx={{ textAlign: 'center', width: '100%' }}>
                                <Typography variant="caption" color="text.secondary">
                                  {pr.enabled ? 'Priority enabled' : 'Priority disabled'}
                                </Typography>
                                {hasCustom && (
                                  <Chip size="small" color="info" label="Custom hint" />
                                )}
                              </Stack>
                            )
                          })()}
                        </>
                      ) : (
                        <>
                          <Box sx={emptySlotSx}>
                            <img src="/arrow_plus.png" width={THUMB} />
                          </Box>
                          <Typography variant="body2" color="text.secondary">Select</Typography>
                        </>
                      )}
                    </Stack>
                  </CardActionArea>

                  {sel && (
                    <Tooltip title="Customize event options">
                      <Box
                        role="button"
                        onClick={(e) => { e.stopPropagation(); openOptionsForSupport(idx) }}
                        sx={{
                          position:'absolute', top:6, right:6, width:28, height:28, display:'grid',
                          placeItems:'center', borderRadius:2, bgcolor:'background.paper',
                          border:'2px solid', borderColor:'black', cursor:'pointer'
                        }}
                      >
                        <EditIcon fontSize="small" />
                      </Box>
                    </Tooltip>
                  )}
                  {sel && (
                    <Tooltip title="Hint priority settings">
                      <Box
                        role="button"
                        onClick={(e) => { e.stopPropagation(); setPrioritySlot(idx) }}
                        sx={{
                          position:'absolute', top:6, left:6, width:28, height:28, display:'grid',
                          placeItems:'center', borderRadius:2, bgcolor:'background.paper',
                          border:'2px solid', borderColor:'black', cursor:'pointer'
                        }}
                      >
                        <PriorityHighIcon fontSize="small" />
                      </Box>
                    </Tooltip>
                  )}
                </Card>
              </Box>
            ))}
          </Stack>
        </CardContent>
      </Card>

      {/* Scenario + Trainee (side-by-side) */}
      <Stack direction={{ xs:'column', md:'row' }} spacing={2}>
        {/* Scenario */}
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle1">Scenario</Typography>
            </Stack>
            <Box sx={{ maxWidth: 280 }}>
              <Card variant="outlined" sx={{ position:'relative' }}>
                <CardActionArea onClick={() => setScenarioOpen(true)}>
                  <Stack alignItems="center" spacing={1} sx={{ p: 1 }}>
                    {scenario ? (
                      <>
                        <SmartImage candidates={scenarioImageCandidates(scenario.name || "")} alt={scenario.name} width={THUMB} rounded={8}/>
                        <Typography variant="body2" noWrap>{scenario.name}</Typography>
                      </>
                    ) : (
                      <>
                        <Box sx={emptySlotSx}>
                          <img src="/arrow_plus.png" width={THUMB} />
                        </Box>
                        <Typography variant="body2" color="text.secondary">Select</Typography>
                      </>
                    )}
                  </Stack>
                </CardActionArea>
                {scenario && (
                  <Tooltip title="Customize event options">
                    <Box role="button" onClick={(e)=>{e.stopPropagation(); openOptionsForScenario()}}
                      sx={{ position:'absolute', top:6, right:6, width:28, height:28, display:'grid', placeItems:'center',
                        borderRadius:2, bgcolor:'background.paper', border:'2px solid', borderColor:'black', cursor:'pointer' }}>
                      <EditIcon fontSize="small" />
                    </Box>
                  </Tooltip>
                )}
              </Card>
            </Box>
          </CardContent>
        </Card>
        {/* Trainee */}
        <Card variant="outlined" sx={{ flex: 1 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Typography variant="subtitle1">Trainee</Typography>
            </Stack>
            <Box sx={{ maxWidth: 280 }}>
              <Card variant="outlined" sx={{ position:'relative' }}>
                <CardActionArea onClick={() => setTraineeOpen(true)}>
                  <Stack alignItems="center" spacing={1} sx={{ p: 1 }}>
                    {trainee ? (
                      <>
                        <SmartImage candidates={traineeImageCandidates(trainee.name)} alt={trainee.name || ""} width={THUMB} height={THUMB_H} rounded={8}/>
                        <Typography variant="body2" noWrap>{trainee.name}</Typography>
                      </>
                    ) : (
                      <>
                        <Box sx={emptySlotSx}>
                          <img src="/arrow_plus.png" width={THUMB} />
                        </Box>
                        <Typography variant="body2" color="text.secondary">Select</Typography>
                      </>
                    )}
                  </Stack>
                </CardActionArea>
                {trainee && (
                  <Tooltip title="Customize event options">
                    <Box role="button" onClick={(e)=>{e.stopPropagation(); openOptionsForTrainee()}}
                      sx={{ position:'absolute', top:6, right:6, width:28, height:28, display:'grid', placeItems:'center',
                        borderRadius:1, bgcolor:'background.paper', border:'2px solid', borderColor:'black', cursor:'pointer' }}>
                      <EditIcon fontSize="small" />
                    </Box>
                  </Tooltip>
                )}
              </Card>
            </Box>
          </CardContent>
        </Card>
      </Stack>


      {/* dialogs */}
      <SupportPickerDialog
        open={pickSlot !== null}
        onClose={() => setPickSlot(null)}
        index={index}
        onPick={(s) => {
          if (pickSlot == null) return
          const rarity = (s.rarity === 'SSR' || s.rarity === 'SR' || s.rarity === 'R') ? s.rarity : 'SR'
          setSupport(pickSlot, { name: s.name, rarity, attribute: s.attribute })
          setPickSlot(null)
        }}
      />
      <ScenarioPickerDialog
        open={scenarioOpen}
        onClose={() => setScenarioOpen(false)}
        scenarios={index.scenarios}
        onPick={(s)=>{ setScenario({ name: s.name }); setScenarioOpen(false) }}
      />
      <TraineePickerDialog
        open={traineeOpen}
        onClose={() => setTraineeOpen(false)}
        trainees={Array.from(((index.trainees as any)?.specific ?? new Map()).values()) as TraineeSet[]}
        onPick={(t)=>{ setTrainee({ name: t.name }); setTraineeOpen(false) }}
      />

      {optionsFor && (
        <EventOptionsDialog
          open
          onClose={() => setOptionsFor(null)}
          title={optionsFor.title}
          items={optionsFor.items}
          type={optionsFor.type}
          onPick={(keyStep, pick) => { setOverride(keyStep, pick) }}
        />
      )}

      <SupportPriorityDialog
        open={prioritySlot !== null}
        support={prioritySlot != null ? supports[prioritySlot] : null}
        onClose={() => setPrioritySlot(null)}
      />
    </Stack>
  )
}
