import { Paper, Stack, Typography } from '@mui/material'

export default function Section({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2.5 }}>
      <Stack spacing={2}>
        <Typography variant="h6">{title}</Typography>
        {children}
      </Stack>
    </Paper>
  )
}
