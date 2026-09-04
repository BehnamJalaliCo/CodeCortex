import { useEffect, useMemo, useState } from 'react'
import './GraphExplorer.css'

type Node = { id: string; name: string; kind: string; path: string | null; line: number | null }
type Edge = { source: string; target: string; kind: string; confidence: number | null }
type Payload = { nodes: Node[]; edges: Edge[] }

const emptyPayload: Payload = { nodes: [], edges: [] }

function asPayload(value: unknown): Payload {
  if (!value || typeof value !== 'object') return emptyPayload
  const candidate = value as Partial<Payload>
  return {
    nodes: Array.isArray(candidate.nodes) ? candidate.nodes : [],
    edges: Array.isArray(candidate.edges) ? candidate.edges : [],
  }
}

export function GraphExplorer({ repositoryId }: { repositoryId: string }) {
  const [query, setQuery] = useState('')
  const [relation, setRelation] = useState('')
  const [data, setData] = useState<Payload>(emptyPayload)
  const [selected, setSelected] = useState<Node | null>(null)

  useEffect(() => {
    if (!repositoryId) return
    const timer = setTimeout(() => {
      const parameters = new URLSearchParams({ depth: '2' })
      if (query) parameters.set('query', query)
      if (relation) parameters.set('relation', relation)
      fetch(`/api/v1/repositories/${repositoryId}/graph?${parameters}`)
        .then(response => response.ok ? response.json() : emptyPayload)
        .then(asPayload)
        .then(setData)
        .catch(() => setData(emptyPayload))
    }, 180)
    return () => clearTimeout(timer)
  }, [repositoryId, query, relation])

  const nodes = useMemo(() => data.nodes.slice(0, 80), [data])
  const positions = useMemo(() => new Map(nodes.map((node, index) => {
    const angle = Math.PI * 2 * index / Math.max(1, nodes.length)
    const ring = 115 + index % 3 * 62
    return [node.id, { x: 360 + Math.cos(angle) * ring, y: 250 + Math.sin(angle) * ring }]
  })), [nodes])
  const visible = new Set(nodes.map(node => node.id))
  const edges = data.edges.filter(edge => visible.has(edge.source) && visible.has(edge.target)).slice(0, 180)

  if (!repositoryId) return null

  return <section className="workspaceManager graphSection">
    <div className="sectionHead"><div><div className="eyebrow">GRAPH EXPLORER</div><h3>Dependencies & calls</h3></div><span>{data.nodes.length} nodes · {data.edges.length} edges</span></div>
    <div className="graphTools"><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Focus symbol or file…"/><select value={relation} onChange={event => setRelation(event.target.value)}><option value="">All relations</option><option>calls</option><option>imports</option><option>defines</option><option>contains</option><option>inherits</option><option>references</option></select></div>
    <div className="graphLayout"><article className="panel graphCanvas"><svg viewBox="0 0 720 500">{edges.map((edge, index) => { const start = positions.get(edge.source); const end = positions.get(edge.target); return start && end ? <line key={`${edge.source}-${edge.target}-${index}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} className={`edge ${edge.kind}`}/> : null })}{nodes.map(node => { const position = positions.get(node.id)!; return <g key={node.id} onClick={() => setSelected(node)} className="graphNode"><circle cx={position.x} cy={position.y} r={selected?.id === node.id ? 8 : 5}/><text x={position.x + 9} y={position.y + 4}>{node.name.slice(0, 22)}</text></g> })}</svg></article><aside className="panel nodeInspector"><div className="panelTitle"><span>Node inspector</span><small>{selected?.kind ?? 'Select a node'}</small></div>{selected ? <div className="inspectorBody"><h4>{selected.name}</h4><div className="kv"><span>Kind</span><b>{selected.kind}</b></div><div className="kv"><span>Path</span><b className="mono">{selected.path ?? '—'}</b></div><div className="kv"><span>Line</span><b>{selected.line ?? '—'}</b></div><div className="kv"><span>Incoming</span><b>{data.edges.filter(edge => edge.target === selected.id).length}</b></div><div className="kv"><span>Outgoing</span><b>{data.edges.filter(edge => edge.source === selected.id).length}</b></div></div> : <div className="empty">Click a graph node to inspect it.</div>}</aside></div>
  </section>
}
