import { Container, Stack, Box, Tabs, Tab, Paper } from '@mui/material'
import GeneralForm from '@/components/general/GeneralForm'
import SaveLoadBar from '@/components/common/SaveLoadBar'
import { useEffect, useRef, useState } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useNavPrefsStore } from '@/store/navPrefsStore'
import PresetsShell from '@/components/presets/PresetsShell'
import DailyRacePrefs from '@/components/nav/DailyRacePrefs'

export default function Home() {
  const saveLocal = useConfigStore((s) => s.saveLocal)
  const config = useConfigStore((s) => s.config)
  const collapsed = useConfigStore((s) => s.uiGeneralCollapsed)
  const [tab, setTab] = useState<'scenario' | 'daily'>('scenario')
  const configLoadedRef = useRef(false)

  useEffect(() => {
    const configState = useConfigStore.getState()
    if (!configLoadedRef.current) {
      configState.loadLocal()
      configLoadedRef.current = true
    }

    const navState = useNavPrefsStore.getState()
    if (!navState.loaded && !navState.loading) {
      navState.load().catch(() => {})
    }
  }, [])

  // auto-save (debounced) whenever config changes
  useEffect(() => {
    const t = setTimeout(() => saveLocal(), 300)
    return () => clearTimeout(t)
  }, [config, saveLocal])

  return (
    <Container maxWidth="xl" sx={{ py: 4, px: { xs: 2, sm: 3 } }}>
      <Stack spacing={3}>
        <Paper
          elevation={6}
          sx={{
            borderRadius: 4,
            px: { xs: 1.5, sm: 3 },
            py: { xs: 1.5, sm: 2 },
            bgcolor: (theme) => theme.palette.mode === 'dark' ? theme.palette.background.paper : '#ffffff',
            border: (theme) => `1px solid ${theme.palette.divider}`,
          }}
        >
          <Tabs
            value={tab}
            onChange={(_, next) => setTab(next)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              '& .MuiTab-root': {
                minHeight: 60,
                textTransform: 'uppercase',
                fontWeight: 800,
                letterSpacing: 0.75,
                fontSize: { xs: 15, sm: 16 },
                px: { xs: 2, sm: 3 },
              },
              '& .MuiTabs-indicator': {
                display: 'flex',
                justifyContent: 'center',
                height: 0,
              },
              '& .MuiTabs-indicatorSpan': {
                maxWidth: 60,
                width: '100%',
                borderRadius: 999,
                borderBottom: (theme) => `4px solid ${theme.palette.primary.main}`,
              },
              '& .MuiTab-root.Mui-selected': {
                color: (theme) => theme.palette.primary.main,
              },
              '& .MuiTab-root:not(.Mui-selected)': {
                color: (theme) => theme.palette.text.secondary,
              },
            }}
            TabIndicatorProps={{ children: <span className="MuiTabs-indicatorSpan" /> }}
            textColor="primary"
            indicatorColor="primary"
          >
            <Tab value="scenario" label="Scenario setup" />
            <Tab value="daily" label="Daily races" />
          </Tabs>
        </Paper>

        <Box sx={{ display: tab === 'scenario' ? 'block' : 'none' }}>
          <Box
            sx={{
              display: 'grid',
              gap: 3,
              gridTemplateColumns: {
                xs: '1fr',
                md: collapsed ? '1fr' : 'minmax(320px, 1fr) minmax(0, 2fr)',
                lg: collapsed ? '1fr' : 'minmax(360px, 1fr) minmax(0, 2fr)',
              },
              alignItems: 'start',
              '& > .col': { minWidth: 0, width: '100%' },
            }}
          >
            <Box className="col">
              <Stack spacing={3}>
                <GeneralForm />
              </Stack>
            </Box>

            <Box className="col">
              <Stack spacing={3}>
                <PresetsShell compact={collapsed} />
              </Stack>
            </Box>
          </Box>

          <Stack sx={{ alignItems: 'center' }}>
            <SaveLoadBar />
          </Stack>
        </Box>
        <Box sx={{ display: tab === 'daily' ? 'flex' : 'none', justifyContent: 'center' }}>
          <Box sx={{ width: '100%', maxWidth: 540 }}>
            <DailyRacePrefs />
          </Box>
        </Box>
      </Stack>
    </Container>
  )
}
