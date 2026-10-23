import { useState } from 'react'
import { BookOpen, ChevronDown, ChevronRight, FileText } from 'lucide-react'
import type { DocumentCitation } from '../../types/chat'

export function CitationList({
  citations,
}: {
  citations: DocumentCitation[]
}) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (!citations || citations.length === 0) {
    return null
  }

  return (
    <div className="pt-2 border-t border-slate-100 space-y-1.5">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-slate-500">
        <BookOpen className="h-3 w-3 text-blue-600" />
        <span>Verified Policy Citations ({citations.length}):</span>
      </div>

      <div className="space-y-1.5">
        {citations.map((cite) => {
          const isExpanded = expandedId === cite.citation_id
          return (
            <div
              key={cite.citation_id}
              className="rounded-lg border border-blue-200/80 bg-blue-50/40 text-xs overflow-hidden transition-all"
            >
              <button
                type="button"
                onClick={() =>
                  setExpandedId(isExpanded ? null : cite.citation_id)
                }
                className="w-full px-3 py-2 flex items-center justify-between text-left hover:bg-blue-100/50 transition-colors gap-2"
                aria-expanded={isExpanded}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-600 text-white font-mono text-[10px] font-semibold shrink-0">
                    <FileText className="h-2.5 w-2.5" />
                    {cite.citation_id}
                  </span>
                  <span className="font-semibold text-slate-800 truncate text-[11px]">
                    {cite.document_title}
                  </span>
                  <span className="text-[10px] text-slate-500 shrink-0 hidden sm:inline">
                    ({cite.version} &middot; p.{cite.page_number})
                  </span>
                </div>

                <div className="flex items-center gap-1.5 shrink-0 text-slate-400">
                  <span className="text-[10px] font-mono text-blue-700 hidden md:inline">
                    {cite.section_title}
                  </span>
                  {isExpanded ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </div>
              </button>

              {isExpanded && (
                <div className="px-3 py-2.5 border-t border-blue-200/60 bg-white space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-500">
                    <span className="font-medium text-slate-700">
                      {cite.section_title}
                    </span>
                    <span className="font-mono">
                      Effective: {cite.effective_date} &middot; Page{' '}
                      {cite.page_number} &middot; Relevance:{' '}
                      {Math.round(cite.similarity_score * 100)}%
                    </span>
                  </div>
                  <blockquote className="p-2.5 rounded-md bg-slate-50 border-l-2 border-blue-500 text-[11px] text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                    {cite.excerpt}
                  </blockquote>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
