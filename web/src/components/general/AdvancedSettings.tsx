import {
  Box, Collapse, Divider, FormControlLabel, MenuItem, Select, Slider, Stack, Switch, TextField, Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'
import FieldRow from '@/components/common/FieldRow'
import { useConfigStore } from '@/store/configStore'

export default function AdvancedSettings() {
  const { config, setGeneral } = useConfigStore()
  const [open, setOpen] = useState(false)
  const a = config.general.advanced

  const [autoRest, setAutoRest] = useState(a.autoRestMinimum)
  const [skillInterval, setSkillInterval] = useState(a.skillCheckInterval)
  const [skillDelta, setSkillDelta] = useState(a.skillPtsDelta)
  const [undertrain, setUndertrain] = useState(a.undertrainThreshold)
  const [topStats, setTopStats] = useState(a.topStatsFocus)

  const autoRestMarks = useMemo(() => {
    const marks = [{ value: 1 }]
    for (let v = 5; v <= 70; v += 5) {
      marks.push({ value: v })
    }
    return marks
  }, [])

  const toNumber = (val: number | number[]) => (Array.isArray(val) ? val[0] : val)

  useEffect(() => {
    setAutoRest(a.autoRestMinimum)
    setSkillInterval(a.skillCheckInterval)
    setSkillDelta(a.skillPtsDelta)
    setUndertrain(a.undertrainThreshold)
    setTopStats(a.topStatsFocus)
  }, [
    a.autoRestMinimum,
    a.skillCheckInterval,
    a.skillPtsDelta,
    a.undertrainThreshold,
    a.topStatsFocus,
  ])

  const commitAdvanced = <K extends keyof typeof a>(key: K, value: (typeof a)[K]) => {
    setGeneral({
      advanced: {
        ...a,
        [key]: value,
      },
    })
  }
  const sliderSx = {
    width: '100%',
    '.MuiSlider-thumb': {
      width: 12,
      height: 12,
      boxShadow: 'none',
    },
    '.MuiSlider-thumb::before': {
      boxShadow: 'none',
    },
    '.MuiSlider-rail': {
      height: 4,
      borderRadius: 2,
    },
    '.MuiSlider-track': {
      height: 4,
      borderRadius: 2,
    },
    '.MuiSlider-valueLabel': {
      background: 'transparent',
      color: 'inherit',
      padding: 0,
      borderRadius: 0,
      fontSize: 16,
      fontWeight: 800,
      transform: 'translate(0%, 30px) scale(1)',
      '&:before': { display: 'none' },
    },
  } as const
  const controlWrapSx = (theme: any) => ({
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: 1,
    px: 1.5,
    pt: 1.5,
    pb: 3.5,
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: 1.5,
    backgroundColor:
      theme.palette.mode === 'dark'
        ? theme.palette.background.default
        : theme.palette.grey[50],
    boxShadow: theme.palette.mode === 'dark'
      ? 'inset 0 0 0 1px rgba(255,255,255,0.05)'
      : '0 1px 2px rgba(15, 23, 42, 0.08)',
    maxWidth: 240,
    width: '100%',
  })

  return (
    <Stack spacing={1.5}>
      <Typography
        variant="subtitle1"
        sx={{ cursor: 'pointer', userSelect: 'none' }}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '▼' : '▶'} Advanced settings
      </Typography>

      <Collapse in={open}>
        <Divider sx={{ mb: 2 }} />

        <FieldRow
          label="Hotkey"
          control={
            <Select
              size="small"
              value={a.hotkey}
              onChange={(e) => setGeneral({ advanced: { ...a, hotkey: e.target.value as any } })}
            >
              {['F1', 'F2', 'F3', 'F4'].map((k) => (
                <MenuItem key={k} value={k}>{k}</MenuItem>
              ))}
            </Select>
          }
          info="Keyboard key to toggle the agent on/off."
        />

        <FieldRow
          label="Debug mode"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={a.debugMode}
                  onChange={(e) => setGeneral({ advanced: { ...a, debugMode: e.target.checked } })}
                />
              }
              label={a.debugMode ? 'Enabled' : 'Disabled'}
            />
          }
          info="Enable debug mode for verbose logging and extra overlays."
        />

        <FieldRow
          label="Use external processor"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={a.useExternalProcessor}
                  onChange={(e) =>
                    setGeneral({ advanced: { ...a, useExternalProcessor: e.target.checked } })
                  }
                />
              }
              label={a.useExternalProcessor ? 'Enabled' : 'Disabled'}
            />
          }
          info="Send OCR/YOLO processing to a remote server."
        />

        <FieldRow
          label="External processor URL"
          control={
            <TextField
              size="small"
              fullWidth
              value={a.externalProcessorUrl}
              onChange={(e) => setGeneral({ advanced: { ...a, externalProcessorUrl: e.target.value } })}
              disabled={!a.useExternalProcessor}
              placeholder="http://127.0.0.1:8001"
            />
          }
          info="Base URL for the remote inference server."
        />

        <FieldRow
          label="Auto rest minimum"
          info="Below this energy% the bot will rest automatically."
          control={
            <Box sx={controlWrapSx}>
              <Slider
                value={autoRest}
                onChange={(_, v) => {
                  const raw = toNumber(v)
                  const next = raw <= 1 ? 1 : Math.max(5, Math.min(70, Math.round(raw / 5) * 5))
                  setAutoRest(next)
                }}
                onChangeCommitted={(_, v) => {
                  const raw = toNumber(v)
                  const next = raw <= 1 ? 1 : Math.max(5, Math.min(70, Math.round(raw / 5) * 5))
                  setAutoRest(next)
                  commitAdvanced('autoRestMinimum', next)
                }}
                min={1}
                max={70}
                step={1}
                marks={autoRestMarks}
                sx={sliderSx}
                valueLabelDisplay="on"
                valueLabelFormat={(v) => `${v}%`}
              />
            </Box>
          }
          sx={{ mt: 2 }}
        />

        <FieldRow
          label="Skills: check interval"
          info="How often to reopen the Skills shop during races — 1 checks every turn, 3 checks every third turn."
          control={
            <Box sx={controlWrapSx}>
              <Slider
                value={skillInterval}
                onChange={(_, v) => {
                  const next = Math.max(1, Math.min(5, Math.round(toNumber(v))))
                  setSkillInterval(next)
                }}
                onChangeCommitted={(_, v) => {
                  const next = Math.max(1, Math.min(5, Math.round(toNumber(v))))
                  setSkillInterval(next)
                  commitAdvanced('skillCheckInterval', next)
                }}
                min={1}
                max={5}
                step={1}
                sx={sliderSx}
                valueLabelDisplay="on"
              />
            </Box>
          }
          sx={{ mt: 2 }}
        />

        <FieldRow
          label="Skills: points delta"
          info="Reopen the Skills shop only after earning at least this many points (e.g. 60 waits until you gain 60 more points)."
          control={
            <Box sx={controlWrapSx}>
              <Slider
                value={skillDelta}
                onChange={(_, v) => {
                  const raw = toNumber(v)
                  const next = Math.max(60, Math.min(200, Math.round(raw / 10) * 10))
                  setSkillDelta(next)
                }}
                onChangeCommitted={(_, v) => {
                  const raw = toNumber(v)
                  const next = Math.max(60, Math.min(200, Math.round(raw / 10) * 10))
                  setSkillDelta(next)
                  commitAdvanced('skillPtsDelta', next)
                }}
                min={60}
                max={200}
                step={10}
                sx={sliderSx}
                valueLabelDisplay="on"
              />
            </Box>
          }
          sx={{ mt: 2 }}
        />

        <FieldRow
          label="Undertrain threshold"
          info="Lower values make detection stricter, higher values more forgiving. The system looks at how much each stat contributes to your total stats and compares it with how much it should contribute based on the ideal balance. Think of it as checking if any stat is falling behind or getting too far ahead. For example, if your total stats add up to 1640 and SPD is 375, that means SPD makes up about 23% of your total. But according to the ideal setup, SPD should represent 32% — which would be around 525 points. That means SPD is about 9% lower than where it should be, so it’s undertrained. However, if your undertraining threshold is 10%, the bot won’t force SPD training yet because the difference isn’t big enough. On the other hand, PWR is 512, which is 31% of the total, while its ideal ratio is 25%, so it’s 7% higher than expected — meaning PWR is overtrained and should be paused until the others catch up."
          control={
            <Box sx={controlWrapSx}>
              <Slider
                value={undertrain}
                onChange={(_, v) => {
                  const next = Math.max(1, Math.min(20, Math.round(toNumber(v))))
                  setUndertrain(next)
                }}
                onChangeCommitted={(_, v) => {
                  const next = Math.max(1, Math.min(20, Math.round(toNumber(v))))
                  setUndertrain(next)
                  commitAdvanced('undertrainThreshold', next)
                }}
                min={1}
                max={20}
                step={1}
                sx={sliderSx}
                valueLabelDisplay="on"
                valueLabelFormat={(v) => `${v}%`}
              />
            </Box>
          }
          sx={{ mt: 2 }}
        />

        <FieldRow
          label="Top stats focus"
          info="Used to re-prioritize stats when training and also if bot finds a low SV value in priority stat compared with maximum SV value in another tile. If difference is not more than 0.75 we skip the 'best' option and get the second best option only if it is in these first top stats"
          control={
            <Box sx={controlWrapSx}>
              <Slider
                value={topStats}
                onChange={(_, v) => {
                  const next = Math.max(1, Math.min(5, Math.round(toNumber(v))))
                  setTopStats(next)
                }}
                onChangeCommitted={(_, v) => {
                  const next = Math.max(1, Math.min(5, Math.round(toNumber(v))))
                  setTopStats(next)
                  commitAdvanced('topStatsFocus', next)
                }}
                min={1}
                max={5}
                sx={sliderSx}
                valueLabelDisplay="on"
                marks
              />
            </Box>
          }
          sx={{ mt: 2 }}
        />
      </Collapse>
    </Stack>
  )
}
