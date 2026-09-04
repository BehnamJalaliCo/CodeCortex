import {useEffect, useMemo, useState} from 'react'

import {GitIntelligence} from './components/GitIntelligence'
import {GraphExplorer} from './components/GraphExplorer'
import {PlatformCenters} from './components/PlatformCenters'
import {RepositoryExplorer} from './components/RepositoryExplorer'
import {WorkspaceManager} from './components/WorkspaceManager'

type Health = {status: string; version: string}
type Repository = {
  repository_id: string
  workspace: string
  name: string
  root: string
  created_at: string
}
type Overview = {
  repository: {root: string; languages: [string, number][]}
  index: {tracked: number; files_reparsed: number; duration_ms: number}
  graph: {nodes: number; edges: number; symbols: number}
  git: {commits: number; hot_files: string[]}
  runtime: {health: Record<string, boolean>; active_backends: string[]}
}

const fmt = (value: number) => new Intl.NumberFormat().format(value)

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [selected, setSelected] = useState('')
  const [overview, setOverview] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshRepositories = () =>
    fetch('/api/v1/repositories')
      .then(response => (response.ok ? response.json() : []))
      .then((items: Repository[]) => {
        setRepositories(items)
        setSelected(current => current || items[0]?.repository_id || '')
      })

  useEffect(() => {
    fetch('/api/v1/health')
      .then(response => response.json())
      .then(setHealth)
      .catch(() => setError('API unavailable'))
    void refreshRepositories()
  }, [])

  useEffect(() => {
    if (!selected) {
      setOverview(null)
      return
    }
    fetch(`/api/v1/repositories/${selected}/overview`)
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<Overview>
      })
      .then(setOverview)
      .catch(reason => setError(reason instanceof Error ? reason.message : 'Overview failed'))
  }, [selected])

  const healthy = useMemo(
    () => (overview ? Object.values(overview.runtime.health).filter(Boolean).length : 0),
    [overview],
  )
  const total = overview ? Object.keys(overview.runtime.health).length : 0
  const cards = [
    ['Indexed files', overview ? fmt(overview.index.tracked) : '—'],
    ['Symbols', overview ? fmt(overview.graph.symbols) : '—'],
    ['Graph nodes', overview ? fmt(overview.graph.nodes) : '—'],
    ['Graph edges', overview ? fmt(overview.graph.edges) : '—'],
    ['Git commits', overview ? fmt(overview.git.commits) : '—'],
    ['Engine health', overview ? `${healthy}/${total}` : '—'],
  ]

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="mark">C</span>
          <span>CodeCortex</span>
        </div>
        <nav>
          <a className="active" href="#overview">Overview</a>
          <a href="#workspaces">Workspaces</a>
          <a href="#intelligence">Intelligence</a>
          <a href="#graph">Graph</a>
          <a href="#git">Git</a>
          <a href="#quality">Quality</a>
          <a href="#cluster">Cluster</a>
          <a href="#observability">Runtime</a>
          <a href="#administration">Administration</a>
        </nav>
      </aside>
      <main className="content">
        <header className="topbar">
          <div>
            <div className="eyebrow">CONTROL PLANE</div>
            <h1>Console</h1>
          </div>
          <div className="toolbar">
            <label
              htmlFor="repository-select"
              style={{
                position: 'absolute',
                width: 1,
                height: 1,
                padding: 0,
                margin: -1,
                overflow: 'hidden',
                clip: 'rect(0, 0, 0, 0)',
                whiteSpace: 'nowrap',
                border: 0,
              }}
            >
              Repository
            </label>
            <select
              id="repository-select"
              aria-label="Repository"
              value={selected}
              onChange={event => setSelected(event.target.value)}
            >
              <option value="">No repository</option>
              {repositories.map(repository => (
                <option key={repository.repository_id} value={repository.repository_id}>
                  {repository.workspace} / {repository.name}
                </option>
              ))}
            </select>
            <div className={`status ${error ? 'bad' : health ? 'good' : ''}`}>
              <span className="dot" />
              {error ? 'API issue' : health ? `API ${health.version}` : 'Connecting'}
            </div>
          </div>
        </header>
        <section className="hero" id="overview">
          <div>
            <div className="eyebrow">CODE INTELLIGENCE</div>
            <h2>
              {repositories.find(repository => repository.repository_id === selected)?.name
                ?? 'One control plane for repository intelligence.'}
            </h2>
            <p>{overview?.repository.root ?? 'Register a repository to activate live intelligence.'}</p>
          </div>
        </section>
        <section className="metrics">
          {cards.map(([label, value]) => (
            <article className="metric" key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </article>
          ))}
        </section>
        <section className="grid2">
          <article className="panel">
            <div className="panelTitle">
              <span>Runtime health</span>
              <small>{healthy}/{total} healthy</small>
            </div>
            <div className="list">
              {overview ? Object.entries(overview.runtime.health).map(([name, ok]) => (
                <div className="row" key={name}>
                  <span>{name}</span>
                  <b className={ok ? 'ok' : 'fail'}>{ok ? 'Healthy' : 'Unavailable'}</b>
                </div>
              )) : <div className="empty">No runtime selected</div>}
            </div>
          </article>
          <article className="panel">
            <div className="panelTitle">
              <span>Hot files</span>
              <small>Git intelligence</small>
            </div>
            <div className="list">
              {overview?.git.hot_files.length ? overview.git.hot_files.map(path => (
                <div className="row mono" key={path}>{path}</div>
              )) : <div className="empty">No Git activity yet</div>}
            </div>
          </article>
        </section>
        <RepositoryExplorer repositoryId={selected} />
        <div id="graph"><GraphExplorer repositoryId={selected} /></div>
        <GitIntelligence repositoryId={selected} />
        <PlatformCenters repositoryId={selected} />
        <WorkspaceManager onChanged={() => void refreshRepositories()} />
      </main>
    </div>
  )
}
