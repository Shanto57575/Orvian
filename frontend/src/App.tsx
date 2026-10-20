import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from '@tanstack/react-query'
import {
  Activity,
  CheckCircle2,
  Layers,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

interface HealthResponse {
  status: string
  project: string
  environment: string
  debug: boolean
}

async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch('http://127.0.0.1:8000/api/v1/health')
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }
  return response.json()
}

function StatusCard() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
  })

  return (
    <div className="rounded-xl border bg-card p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Activity className="size-5" />
        </div>
        <div>
          <h3 className="font-semibold text-card-foreground">API Health</h3>
          <p className="text-sm text-muted-foreground">
            FastAPI service status check
          </p>
        </div>
      </div>
      <div className="mt-4 pt-4 border-t">
        {isPending ? (
          <p className="text-sm text-muted-foreground animate-pulse">
            Checking backend status...
          </p>
        ) : isError ? (
          <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
            <span className="size-2 rounded-full bg-amber-500" />
            <span>Backend offline (start FastAPI on port 8000)</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="size-4" />
            <span>
              Backend Online ({data.project} · {data.environment})
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-background text-foreground flex flex-col">
        {/* Top Header */}
        <header className="border-b bg-card">
          <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold">
                O
              </div>
              <span className="font-bold text-lg tracking-tight">Orvian</span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-secondary text-secondary-foreground font-medium">
                Scaffold
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="size-4 text-emerald-500" />
              <span>Synthetic Data Only</span>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-12 flex flex-col gap-8">
          {/* Welcome Banner */}
          <div className="flex flex-col gap-3 max-w-2xl">
            <div className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <Sparkles className="size-3.5 text-primary" />
              <span>Project Foundation Ready</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Orvian Data Assistant
            </h1>
            <p className="text-base text-muted-foreground">
              Initial scaffold and verified development baseline. Core
              application services, authentication, and data retrieval will be
              implemented in subsequent phases.
            </p>
          </div>

          {/* Cards Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <StatusCard />

            <div className="rounded-xl border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Layers className="size-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-card-foreground">
                    Technology Stack
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Verified & strictly typed toolchain
                  </p>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t flex flex-wrap gap-2 text-xs">
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  React 19
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  TypeScript Strict
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  Vite + Tailwind v4
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  TanStack Query
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  FastAPI
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  SQLAlchemy 2 + psycopg 3
                </span>
                <span className="px-2.5 py-1 rounded-md bg-secondary text-secondary-foreground font-medium">
                  Neon pgvector
                </span>
              </div>
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="border-t py-6 text-center text-xs text-muted-foreground">
          Orvian &copy; 2026 &middot; Synthetic Business Data Assistant &middot;
          Project Setup Phase
        </footer>
      </div>
    </QueryClientProvider>
  )
}

export default App
