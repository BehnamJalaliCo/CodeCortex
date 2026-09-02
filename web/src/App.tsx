import { useEffect, useState } from 'react'

type Health = { status: string; version: string }

export function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/v1/health')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        return response.json() as Promise<Health>
      })
      .then(setHealth)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : 'API unavailable'))
  }, [])

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="mark">C</span><span>CodeCortex</span></div>
        <nav>
          <a className="active" href="#overview">Overview</a>
          <a href="#workspaces">Workspaces</a>
          <a href="#intelligence">Intelligence</a>
          <a href="#runtime">Runtime</a>
          <a href="#administration">Administration</a>
        </nav>
      </aside>
      <main className="content">
        <header className="topbar">
          <div><div className="eyebrow">CONTROL PLANE</div><h1>Console</h1></div>
          <div className={`status ${error ? 'bad' : health ? 'good' : ''}`}>
            <span className="dot" />{error ? 'API offline' : health ? `API ${health.version}` : 'Connecting'}
          </div>
        </header>
        <section className="hero" id="overview">
          <div><div className="eyebrow">CODE INTELLIGENCE</div><h2>One control plane for repository intelligence.</h2><p>Graph, context, retrieval, traces, quality and distributed operations share one CodeCortex core.</p></div>
        </section>
      </main>
    </div>
  )
}
