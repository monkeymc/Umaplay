import { Paper, Stack, Typography } from '@mui/material';
import { useTheme, alpha } from '@mui/material/styles';

export default function Section({
  title,
  children,
  footer,
  sx,
  contentSx,
}: {
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
  sx?: any
  contentSx?: any
}) {
  const theme = useTheme()
  return (
    <Paper
      elevation={1}
      sx={{
        borderRadius: 2,
        p: 3,
        transition: 'border-color 120ms ease',
        maxWidth: sx?.maxWidth ?? '680px',
        border: sx?.variant === 'plain' ? 'none' : `1px solid ${alpha(theme.palette.divider, 0.8)}`,
        boxShadow: sx?.variant === 'plain' ? 'none' : undefined,
        '&:hover': sx?.variant === 'plain'
          ? undefined
          : {
              borderColor: alpha(theme.palette.primary.main, 0.4),
              boxShadow: `${alpha(theme.palette.primary.main, 0.15)} 0 8px 24px -12px`,
            },
        ...sx,
      }}
    >
      <Stack spacing={2} sx={contentSx}>
        <Typography variant="h6">{title}</Typography>
        {children}
        {footer}
      </Stack>
    </Paper>
  )
}
