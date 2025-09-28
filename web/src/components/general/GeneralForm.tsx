import {
  Accordion, AccordionDetails, AccordionSummary,
  FormControlLabel, MenuItem, Select, Slider, Box, Stack, Switch, TextField, Typography, Button, Snackbar, Alert,
  Tooltip, IconButton, Avatar,
} from '@mui/material'
import KeyboardDoubleArrowLeftIcon from '@mui/icons-material/KeyboardDoubleArrowLeft'
import KeyboardDoubleArrowRightIcon from '@mui/icons-material/KeyboardDoubleArrowRight'
import Section from '@/components/common/Section'
import FieldRow from '@/components/common/FieldRow'
import { useConfigStore } from '@/store/configStore'
import AdvancedSettings from './AdvancedSettings'
import { checkUpdate, updateFromGithub } from '@/services/api'
import { useEffect, useState } from 'react'

export default function GeneralForm() {
  const { config, setGeneral } = useConfigStore()
  const uiTheme = useConfigStore((s) => s.uiTheme)
  const setUiTheme = useConfigStore((s) => s.setUiTheme)
  const g = config.general
  const collapsed = useConfigStore((s) => s.uiGeneralCollapsed)
  const setCollapsed = useConfigStore((s) => s.setGeneralCollapsed)
  const [updating, setUpdating] = useState(false)
  const [snack, setSnack] = useState<{open:boolean; msg:string; severity:'success'|'error'}>({open:false,msg:'',severity:'success'})
  const [update, setUpdate] = useState<{is_update_available:boolean; latest?:string; html_url?:string} | null>(null)

  useEffect(() => {
    let mounted = true
    checkUpdate().then(info => {
      if (mounted) setUpdate(info)
    }).catch(() => {})
    return () => { mounted = false }
  }, [])
  // small helper map for mode icons (place PNGs under /public/icons/)
  const MODE_ICON: Record<'steam' | 'scrcpy' | 'bluestack', string> = {
    steam: '/icons/mode_steam.png',
    scrcpy: '/icons/mode_scrcpy.png',
    bluestack: '/icons/mode_bluestack.png',
  }

  return (
    <Section title="">
      {update && update.is_update_available && (
        <Alert severity="info" sx={{ mt: 1 }}>
          New version available: {update.latest}{' '}
          <Button
            size="small"
            onClick={() => window.open(update.html_url || 'https://github.com/YOUR_GH_USERNAME_OR_ORG/YOUR_REPO_NAME/releases/latest', '_blank')}
          >
            Download
          </Button>
        </Alert>
      )}
      <Accordion
        elevation={0}
        expanded={!collapsed}
        onChange={(_, expanded) => setCollapsed(!expanded)}
        sx={{ border: (t) => `1px solid ${t.palette.divider}`, borderRadius: 1 }}
      >
        <AccordionSummary sx={{ '& .MuiAccordionSummary-content': { m: 0 } }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ width: '100%' }}>
            <Typography variant="h6">General configurations</Typography>
            <Tooltip title={collapsed ? 'Expand' : 'Collapse'} placement="left">
              <IconButton component="span" size="small" onClick={() => setCollapsed(!collapsed)}>
                {collapsed ? (
                  <KeyboardDoubleArrowRightIcon fontSize="small" />
                ) : (
                  <KeyboardDoubleArrowLeftIcon fontSize="small" />
                )}
              </IconButton>
            </Tooltip>
          </Stack>
        </AccordionSummary>
        <AccordionDetails>
      <Stack spacing={1}>
        <FieldRow
          label="UI Theme"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={uiTheme === 'dark'}
                  onChange={(e) => setUiTheme(e.target.checked ? 'dark' : 'light')}
                />
              }
              label={uiTheme === 'dark' ? 'Dark' : 'Light'}
            />
          }
          info="Toggle dark/light mode for this configuration UI. (Does not affect in-game visuals.)"
        />
        <FieldRow
          label="Mode"
          control={
            <Select
              size="small"
              value={g.mode}
              onChange={(e) => setGeneral({ mode: e.target.value as any })}
              renderValue={(val) => {
                const m = val as 'steam' | 'scrcpy' | 'bluestack'
                return (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Avatar
                      variant="rounded"
                      src={MODE_ICON[m]}
                      alt={m}
                      sx={{ width: 20, height: 20 }}
                    />
                    <span style={{ textTransform: 'none' }}>{m}</span>
                  </Stack>
                )
              }}
            >
              {(['steam', 'scrcpy', 'bluestack'] as const).map((m) => (
                <MenuItem key={m} value={m}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Avatar
                      variant="rounded"
                      src={MODE_ICON[m]}
                      alt={m}
                      sx={{ width: 20, height: 20 }}
                    />
                    <span style={{ textTransform: 'none' }}>{m}</span>
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          }
          info="Select the platform/controller the agent should target."
        />

        {g.mode === 'scrcpy' && (
          <FieldRow
            label="Window title"
            control={
              <TextField
                size="small"
                value={g.windowTitle}
                onChange={(e) => setGeneral({ windowTitle: e.target.value })}
                placeholder="Your scrcpy device title (e.g. 23117RA68G)"
              />
            }
            info="Exact (or unique substring) of the SCRCPY window title to focus and capture."
          />
        )}

        <FieldRow
          label="Fast mode"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={g.fastMode}
                  onChange={(e) => setGeneral({ fastMode: e.target.checked })}
                />
              }
              label={g.fastMode ? 'Enabled' : 'Disabled'}
            />
          }
          info="Lower-latency settings (might reduce accuracy in edge cases)."
        />

        <FieldRow
          label="Try again on failed goal"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={g.tryAgainOnFailedGoal}
                  onChange={(e) => setGeneral({ tryAgainOnFailedGoal: e.target.checked })}
                />
              }
              label={g.tryAgainOnFailedGoal ? 'Enabled' : 'Disabled'}
            />
          }
          info="If the agent fails to read the goal text, reattempt once."
        />

        <FieldRow
          label="Prioritize hint"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={g.prioritizeHint}
                  onChange={(e) => setGeneral({ prioritizeHint: e.target.checked })}
                />
              }
              label={g.prioritizeHint ? 'Enabled' : 'Disabled'}
            />
          }
          info="Treat hint tiles as more valuable during training decisions."
        />
        <FieldRow
          label="Max Failure %"
          info="Upper bound for allowed failure% on a tile."
          control={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Slider
                value={g.maxFailure}
                onChange={(_, v) => setGeneral({ maxFailure: Number(v) })}
                min={0}
                max={99}
                sx={{ flex: 1 }}
              />
              <Typography variant="body2" sx={{ width: 32, textAlign: 'right' }}>
                {g.maxFailure}
              </Typography>
            </Box>
          }
        />

        <FieldRow
          label="Skill Pts Check"
          control={
            <TextField
              size="small"
              type="number"
              value={g.skillPtsCheck}
              onChange={(e) => setGeneral({ skillPtsCheck: Number(e.target.value || 0) })}
              inputProps={{ min: 0 }}
            />
          }
          info="If skill points ≥ this value in Raceday, the agent opens Skills to buy."
        />

        <FieldRow
          label="Accept consecutive race"
          control={
            <FormControlLabel
              control={
                <Switch
                  checked={g.acceptConsecutiveRace}
                  onChange={(e) => setGeneral({ acceptConsecutiveRace: e.target.checked })}
                />
              }
              label={g.acceptConsecutiveRace ? 'Enabled' : 'Disabled'}
            />
          }
          info="Allows back-to-back racing when conditions are met."
        />

        <AdvancedSettings />

        {/* Update from GitHub (only local, only if branch == main) */}
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
          <Button
            size="small"
            variant="contained"
            disabled={updating}
            onClick={async () => {
              try {
                setUpdating(true)
                const res = await updateFromGithub()
                setSnack({ open: true, msg: `Updated successfully (branch: ${res.branch})`, severity: 'success' })
              } catch (e:any) {
                setSnack({ open: true, msg: e?.message || 'Update failed', severity: 'error' })
              } finally {
                setUpdating(false)
              }
            }}
          >
            {updating ? 'Updating…' : 'Update from GitHub'}
          </Button>
        </Box>

        <Snackbar
          open={snack.open}
          autoHideDuration={2600}
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
      </Stack>
        </AccordionDetails>
      </Accordion>
    </Section>
  )
}
