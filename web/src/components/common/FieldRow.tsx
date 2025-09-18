import { Box, Typography } from '@mui/material'
import InfoToggle from './InfoToggle'

type Props = {
  label: string
  control: React.ReactNode
  info?: React.ReactNode
  sx?: object
}

export default function FieldRow({ label, control, info, sx }: Props) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: 'minmax(160px,220px) 1fr auto',
        gap: 1,
        alignItems: 'center',
        ...sx,
      }}
    >
      <Typography variant="body2" color="text.secondary">{label}</Typography>
      {/* clamp painting to this cell to avoid slider track overflow */}
      <Box sx={{ minWidth: 0, overflow: 'hidden' }}>{control}</Box>
      {info && <InfoToggle>{info}</InfoToggle>}
    </Box>
  )
}
