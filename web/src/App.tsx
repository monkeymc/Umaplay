import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Home from '@/pages/Home'

const qc = new QueryClient()

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <Home />
    </QueryClientProvider>
  )
}
