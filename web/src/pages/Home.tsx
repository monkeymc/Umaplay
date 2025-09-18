import { Container, Stack, Box } from '@mui/material'
import GeneralForm from '@/components/general/GeneralForm'
import SaveLoadBar from '@/components/common/SaveLoadBar'
import { useEffect } from 'react'
import { useConfigStore } from '@/store/configStore'
import PresetsShell from '@/components/presets/PresetsShell'

export default function Home() {
  const loadLocal = useConfigStore((s) => s.loadLocal)
  const saveLocal = useConfigStore((s) => s.saveLocal)
  const config = useConfigStore((s) => s.config)
  const collapsed = useConfigStore((s) => s.uiGeneralCollapsed)

   useEffect(() => {
     loadLocal() // hydrate from local storage on first mount
   }, [loadLocal])

  // auto-save (debounced) whenever config changes
  useEffect(() => {
    const t = setTimeout(() => saveLocal(), 300)
    return () => clearTimeout(t)
  }, [config, saveLocal])

    return (
      <Container maxWidth="xl" sx={{ py: 4, px: { xs: 2, sm: 3 } }}>
      <Box
        sx={{
          display: 'grid',
          gap: 3, // theme.spacing(3)
          gridTemplateColumns: {
                xs: '1fr',
                // full width, 1/3 | 2/3 with sensible minimums
                md: collapsed ? '1fr' : 'minmax(320px, 1fr) minmax(0, 2fr)',
                lg: collapsed ? '1fr' : 'minmax(360px, 1fr) minmax(0, 2fr)',
          },
          alignItems: 'start',
              // make left paper edge align with container padding
              // (keeps visual “left border” neatly aligned)
              '& > .col': { minWidth: 0, width: '100%' },
        }}
      >
        {/* Left column: General configurations */}
        <Box className="col">
          <Stack spacing={3}>
            <GeneralForm />
          </Stack>
        </Box>

        {/* Right column: Presets */}
        <Box className="col">
          <Stack spacing={3}>
            <PresetsShell compact={collapsed} />
          </Stack>
        </Box>
      </Box>
           {/* Sticky save bar across the bottom */}
            <Stack sx={{ mt: 3, alignItems: 'center' }}>
              <SaveLoadBar />
            </Stack>
        </Container>
    )
}
