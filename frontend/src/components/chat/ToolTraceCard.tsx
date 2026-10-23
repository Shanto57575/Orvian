import { useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Database,
  CheckCircle2,
  AlertTriangle,
  Code2,
} from 'lucide-react'
import type { ToolCallTrace } from '../../types/chat'

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  get_revenue_summary: 'Revenue Summary',
  list_unpaid_invoices: 'Unpaid & Overdue Invoices',
  get_customer_summary: 'Customer Account Summary',
  search_customers: 'Customer Search',
  get_monthly_trend: 'Monthly Trend Analysis',
  search_policy_documents: 'Company Policy Document Search',
}

export function ToolTraceCard({ trace }: { trace: ToolCallTrace }) {
  const [isOpen, setIsOpen] = useState(false)
  const friendlyName = TOOL_DISPLAY_NAMES[trace.name] || trace.name

  // Extract high-level summary chips from arguments & results
  const renderSummary = () => {
    if (!trace.ok) {
      return (
        <span className="text-[11px] text-amber-700">
          Error: {trace.error_code || 'Execution failed'}
        </span>
      )
    }

    if (!trace.result) {
      return <span className="text-[11px] text-slate-500">Query executed</span>
    }

    if (trace.name === 'get_revenue_summary') {
      const totals = Array.isArray(trace.result.totals)
        ? trace.result.totals
        : []
      const first = totals[0] as
        | { currency?: string; invoiced?: string; collected?: string }
        | undefined
      if (first) {
        return (
          <span className="text-[11px] font-medium text-slate-700">
            {first.currency || 'USD'} &middot; Invoiced: ${first.invoiced}{' '}
            &middot; Collected: ${first.collected}
          </span>
        )
      }
    }

    if (trace.name === 'list_unpaid_invoices') {
      const totalMatching = Number(trace.result.total_matching ?? 0)
      const returned = Number(trace.result.returned ?? 0)
      const overdue = trace.result.overdue_only ? 'overdue' : 'unpaid'
      return (
        <span className="text-[11px] font-medium text-slate-700">
          Found {totalMatching} {overdue} ({returned} shown)
        </span>
      )
    }

    if (trace.name === 'get_customer_summary') {
      const name =
        typeof trace.result.name === 'string' ? trace.result.name : 'Customer'
      const found = Boolean(trace.result.found)
      return (
        <span className="text-[11px] font-medium text-slate-700">
          {found ? `${name} matched` : 'Customer not found'}
        </span>
      )
    }

    if (trace.name === 'search_customers') {
      const matches = Array.isArray(trace.result.matches)
        ? trace.result.matches
        : []
      return (
        <span className="text-[11px] font-medium text-slate-700">
          {matches.length} customer{matches.length === 1 ? '' : 's'} found
        </span>
      )
    }

    if (trace.name === 'get_monthly_trend') {
      const points = Array.isArray(trace.result.points)
        ? trace.result.points
        : []
      return (
        <span className="text-[11px] font-medium text-slate-700">
          {points.length} monthly data points
        </span>
      )
    }

    if (trace.name === 'search_policy_documents') {
      const returned = Number(trace.result.returned ?? 0)
      const hasEvidence = Boolean(trace.result.has_evidence)
      return (
        <span className="text-[11px] font-medium text-slate-700">
          {hasEvidence
            ? `Retrieved ${returned} policy excerpt${returned === 1 ? '' : 's'}`
            : 'No matching policy excerpts'}
        </span>
      )
    }

    return <span className="text-[11px] text-slate-500">Data retrieved</span>
  }

  return (
    <div className="rounded-lg border border-slate-200/80 bg-slate-50/70 text-xs overflow-hidden transition-all">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-slate-100/70 transition-colors gap-2"
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md ${
              trace.ok
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-amber-100 text-amber-700'
            }`}
          >
            {trace.ok ? (
              <CheckCircle2 className="h-3.5 w-3.5" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5" />
            )}
          </div>
          <span className="font-semibold text-slate-800 truncate">
            {friendlyName}
          </span>
          <span className="text-slate-400 hidden sm:inline">&middot;</span>
          <div className="truncate hidden sm:block">{renderSummary()}</div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 text-slate-400">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 hidden md:inline">
            Tool Call
          </span>
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="px-3 py-2.5 border-t border-slate-200 bg-white space-y-2">
          {/* Arguments */}
          {trace.arguments && Object.keys(trace.arguments).length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500 mb-1">
                <Database className="h-3 w-3" />
                <span>Validated Parameters:</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(trace.arguments).map(([key, val]) => (
                  <span
                    key={key}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-100 text-[11px] font-mono text-slate-700"
                  >
                    <span className="text-slate-400">{key}:</span>
                    <span>
                      {typeof val === 'object'
                        ? JSON.stringify(val)
                        : String(val)}
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Results Summary & Verification */}
          {trace.result && (
            <div>
              <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500 mb-1">
                <Code2 className="h-3 w-3" />
                <span>Query Results:</span>
              </div>
              <pre className="p-2 rounded bg-slate-900 text-slate-100 font-mono text-[10px] overflow-x-auto max-h-40 leading-relaxed">
                {JSON.stringify(trace.result, null, 2)}
              </pre>
            </div>
          )}

          {/* Error output */}
          {!trace.ok && trace.error_code && (
            <div className="p-2 rounded bg-amber-50 text-amber-800 text-[11px]">
              <strong>Query Error:</strong> {trace.error_code}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
