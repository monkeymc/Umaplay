import React from 'react'
import ReactDOM from 'react-dom/client'
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material'
import App from './App'
import { useConfigStore } from '@/store/configStore'

function AppThemeProvider({ children }: { children: React.ReactNode }) {
  const themeMode = useConfigStore((s) => s.uiTheme) // 'dark' | 'light'
  const theme = React.useMemo(
    () => createTheme({ palette: { mode: themeMode } }),
    [themeMode],
  )
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppThemeProvider>
      <App />
    </AppThemeProvider>
  </React.StrictMode>,
)
