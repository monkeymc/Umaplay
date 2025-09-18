import { Stack } from '@mui/material'
import PresetsTabs from './PresetsTabs'
import PresetPanel from './PresetPanel'

export default function PresetsShell({ compact = false }: { compact?: boolean }) {
  return (
    <Stack spacing={2}>
      <PresetsTabs />
      <PresetPanel compact={compact} />
    </Stack>
  )
}
