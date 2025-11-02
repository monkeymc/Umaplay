import { Container, Stack, Box, Tabs, Tab, Paper, Chip } from '@mui/material'
import GeneralForm from '@/components/general/GeneralForm'
import SaveLoadBar from '@/components/common/SaveLoadBar'
import { useEffect, useRef, useState } from 'react'
import { useConfigStore } from '@/store/configStore'
import { useNavPrefsStore } from '@/store/navPrefsStore'
import PresetsShell from '@/components/presets/PresetsShell'
import ShopPrefs from '@/components/nav/ShopPrefs'
import TeamTrialsPrefs from '@/components/nav/TeamTrialsPrefs'

export default function Home() {
  const saveLocal = useConfigStore((s) => s.saveLocal)
  const config = useConfigStore((s) => s.config)
  const getActivePreset = useConfigStore((s) => s.getActivePreset)
  const collapsed = useConfigStore((s) => s.uiGeneralCollapsed)
  const [tab, setTab] = useState<'scenario' | 'shop' | 'team_trials'>('scenario')
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

  const { preset: activePreset } = getActivePreset()

  return (
    <Container maxWidth="xl" sx={{ py: 4, px: { xs: 2, sm: 3 } }}>
      <Stack spacing={3}>
        <Paper
          elevation={1}
          sx={{
            borderRadius: 3,
            overflow: 'hidden',
            bgcolor: (theme) => theme.palette.mode === 'dark' ? theme.palette.background.paper : '#ffffff',
            border: (theme) => `1px solid ${theme.palette.divider}`,
            background: (theme) =>
              theme.palette.mode === 'dark'
                ? theme.palette.background.paper
                : 'linear-gradient(to bottom, #ffffff 0%, #fafafa 100%)',
          }}
        >
          <Tabs
            value={tab}
            onChange={(_, next) => setTab(next)}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              px: { xs: 1, sm: 2 },
              '& .MuiTab-root': {
                minHeight: 56,
                textTransform: 'uppercase',
                fontWeight: 700,
                letterSpacing: 1,
                fontSize: { xs: 13, sm: 14 },
                px: { xs: 2.5, sm: 3.5 },
                py: 1.5,
                transition: 'all 0.2s ease-in-out',
                borderRadius: 2,
                mx: 0.5,
                '&:hover': {
                  bgcolor: (theme) =>
                    theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
                },
              },
              '& .MuiTabs-indicator': {
                display: 'flex',
                justifyContent: 'center',
                height: 3,
                bottom: 8,
              },
              '& .MuiTabs-indicatorSpan': {
                maxWidth: 40,
                width: '100%',
                borderRadius: 999,
                backgroundColor: (theme) => theme.palette.primary.main,
                boxShadow: (theme) => `0 0 8px ${theme.palette.primary.main}40`,
              },
              '& .MuiTab-root.Mui-selected': {
                color: (theme) => theme.palette.primary.main,
                fontWeight: 800,
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
            <Tab value="shop" label="Shop preferences" />
            <Tab value="team_trials" label="Team Trials" />
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
                {activePreset && (
                  <Chip
                    color="primary"
                    variant="filled"
                    icon={<span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffffff', display: 'inline-block' }} />}
                    label={`Active preset: ${activePreset.name || 'Unnamed preset'}`}
                    sx={{
                      alignSelf: 'flex-start',
                      fontWeight: 600,
                      px: 2,
                      py: 0.75,
                      height: 36,
                      borderRadius: 2.5,
                      boxShadow: (theme) => 
                        theme.palette.mode === 'dark'
                          ? `0 2px 8px ${theme.palette.primary.main}66`
                          : `0 2px 8px ${theme.palette.primary.main}44`,
                      bgcolor: (theme) => 
                        theme.palette.mode === 'dark'
                          ? theme.palette.primary.dark
                          : theme.palette.primary.main,
                      color: '#ffffff',
                      border: (theme) => 
                        theme.palette.mode === 'dark'
                          ? `1px solid ${theme.palette.primary.main}`
                          : 'none',
                      '& .MuiChip-icon': {
                        color: '#ffffff',
                        ml: 0,
                        mr: 1,
                      },
                      '& .MuiChip-label': {
                        px: 0,
                        fontSize: { xs: 13, sm: 14 },
                        color: '#ffffff',
                      },
                    }}
                  />
                )}
                <PresetsShell compact={collapsed} />
              </Stack>
            </Box>
          </Box>

          <Stack sx={{ alignItems: 'center' }}>
            <SaveLoadBar />
          </Stack>
        </Box>
        <Box sx={{ display: tab === 'shop' ? 'flex' : 'none', justifyContent: 'center' }}>
          <Box sx={{ width: '100%', maxWidth: 540 }}>
            <ShopPrefs />
          </Box>
        </Box>
        <Box sx={{ display: tab === 'team_trials' ? 'flex' : 'none', justifyContent: 'center' }}>
          <Box sx={{ width: '100%', maxWidth: 540 }}>
            <TeamTrialsPrefs />
          </Box>
        </Box>
      </Stack>
    </Container>
  )
}
