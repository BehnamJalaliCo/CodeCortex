import { useEffect, useState } from 'react'

type FileNode = { id: string; name: string; path: string | null; language: string | null }
type SymbolNode = { id: string; name: string; kind: string; path: string | null; line: number | null; language: string | null; container: string | null }

export function RepositoryExplorer({ repositoryId }: { repositoryId: string }) {
  const [files, setFiles] = useState<FileNode[]>([]), [symbols, setSymbols] = useState<SymbolNode[]>([]), [query, setQuery] = useState('')
  useEffect(() => { if (!repositoryId) return; fetch(`/api/v1/repositories/${repositoryId}/files`).then(r => r.json()).then(data => setFiles(data.files ?? [])) }, [repositoryId])
  useEffect(() => { if (!repositoryId) return; const timer = setTimeout(() => { const suffix = query ? `?query=${encodeURIComponent(query)}` : ''; fetch(`/api/v1/repositories/${repositoryId}/symbols${suffix}`).then(r => r.json()).then(data => setSymbols(data.symbols ?? [])) }, 180); return () => clearTimeout(timer) }, [repositoryId, query])
  if (!repositoryId) return null
  return <section className="workspaceManager" id="intelligence"><div className="sectionHead"><div><div className="eyebrow">REPOSITORY EXPLORER</div><h3>Files & symbols</h3></div><span>{files.length} files · {symbols.length} symbols</span></div><div className="explorerSearch"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search symbols…" /></div><div className="managerGrid"><article className="panel explorer"><div className="panelTitle"><span>Files</span><small>language aware</small></div><div className="scrollList">{files.map(file => <div className="explorerRow" key={file.id}><div className="mono">{file.path ?? file.name}</div><span>{file.language ?? 'text'}</span></div>)}</div></article><article className="panel explorer"><div className="panelTitle"><span>Symbols</span><small>incremental graph</small></div><div className="scrollList">{symbols.map(symbol => <div className="explorerRow" key={symbol.id}><div><b>{symbol.name}</b><small className="mono">{symbol.path}:{symbol.line ?? 1}</small></div><span>{symbol.kind}</span></div>)}</div></article></div></section>
}
