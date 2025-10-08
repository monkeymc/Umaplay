import {
  Box, Collapse, Divider, FormControlLabel, MenuItem, Select, Slider, Stack, Switch, TextField, Typography,
} from '@mui/material'
import { useState } from 'react'
import FieldRow from '@/components/common/FieldRow'
import { useConfigStore } from '@/store/configStore'

export default function AdvancedSettings() {
  const { config, setGeneral } = useConfigStore()
  const [open, setOpen] = useState(false)
  const a = config.general.advanced

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
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Slider
                value={a.autoRestMinimum}
                onChange={(_, v) => setGeneral({ advanced: { ...a, autoRestMinimum: Number(v) } })}
                min={0}
                max={100}
                sx={{ flex: 1 }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => `${v}%`}
              />
              <TextField
                size="small"
                type="number"
                value={a.autoRestMinimum}
                onChange={(e) =>
                  setGeneral({
                    advanced: {
                      ...a,
                      autoRestMinimum: Math.min(100, Math.max(0, Number(e.target.value))),
                    },
                  })
                }
                inputProps={{ min: 0, max: 100, step: 1 }}
                sx={{ width: 80 }}
              />
            </Box>
          }
        />

        <FieldRow
          label="Undertrain threshold"
          info="Stats below this percentage of their target will be prioritized during training."
          control={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Slider
                value={a.undertrainThreshold}
                onChange={(_, v) => setGeneral({ advanced: { ...a, undertrainThreshold: Number(v) } })}
                min={0}
                max={20}
                sx={{ flex: 1 }}
                valueLabelDisplay="auto"
                valueLabelFormat={(v) => `${v}%`}
              />
              <TextField
                size="small"
                type="number"
                value={a.undertrainThreshold}
                onChange={(e) =>
                  setGeneral({
                    advanced: {
                      ...a,
                      undertrainThreshold: Math.min(20, Math.max(0, Number(e.target.value))),
                    },
                  })
                }
                inputProps={{ min: 0, max: 20, step: 1 }}
                sx={{ width: 80 }}
              />
            </Box>
          }
        />

        <FieldRow
          label="Top stats focus"
          info="Number of top stats to prioritize when considering undertraining."
          control={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Slider
                value={a.topStatsFocus}
                onChange={(_, v) => setGeneral({ advanced: { ...a, topStatsFocus: Number(v) } })}
                min={1}
                max={5}
                sx={{ flex: 1 }}
                valueLabelDisplay="auto"
                marks
              />
              <TextField
                size="small"
                type="number"
                value={a.topStatsFocus}
                onChange={(e) =>
                  setGeneral({
                    advanced: {
                      ...a,
                      topStatsFocus: Math.min(5, Math.max(1, Number(e.target.value))),
                    },
                  })
                }
                inputProps={{ min: 1, max: 5, step: 1 }}
                sx={{ width: 80 }}
              />
            </Box>
          }
        />
      </Collapse>
    </Stack>
  )
}
