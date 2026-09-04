import { FormEvent, useEffect, useState } from 'react'

type Workspace = { workspace_id: string; name: string; created_at: string }
type Repository = { repository_id: string; workspace: string; name: string; root: string; created_at: string }

type Props = { onChanged?: () => void }

export function WorkspaceManager({ onChanged }: Props) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [workspace, setWorkspace] = useState('default')
  const [repoName, setRepoName] = useState('')
  const [root, setRoot] = useState('')
  const [message, setMessage] = useState('')

  const refresh = () => Promise.all([
    fetch('/api/v1/workspaces').then(r => r.ok ? r.json() as Promise<Workspace[]> : []),
    fetch('/api/v1/repositories').then(r => r.ok ? r.json() as Promise<Repository[]> : []),
  ]).then(([spaces, repos]) => { setWorkspaces(spaces); setRepositories(repos) })

  useEffect(() => { void refresh() }, [])

  const addWorkspace = async (event: FormEvent) => {
    event.preventDefault()
    const response = await fetch('/api/v1/workspaces', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name: workspace }) })
    setMessage(response.ok ? 'Workspace ready.' : await response.text())
    await refresh(); onChanged?.()
  }

  const addRepository = async (event: FormEvent) => {
    event.preventDefault()
    const response = await fetch('/api/v1/repositories', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ workspace, name: repoName, root }) })
    setMessage(response.ok ? 'Repository registered.' : await response.text())
    if (response.ok) { setRepoName(''); setRoot('') }
    await refresh(); onChanged?.()
  }

  return <section className="workspaceManager" id="workspaces">
    <div className="sectionHead"><div><div className="eyebrow">WORKSPACES</div><h3>Repository control</h3></div><span>{repositories.length} repositories</span></div>
    <div className="managerGrid">
      <form className="panel formPanel" onSubmit={addWorkspace}><label>Workspace name<input value={workspace} onChange={e => setWorkspace(e.target.value)} required /></label><button type="submit">Create workspace</button><div className="chips">{workspaces.map(item => <span key={item.workspace_id}>{item.name}</span>)}</div></form>
      <form className="panel formPanel" onSubmit={addRepository}><label>Repository name<input value={repoName} onChange={e => setRepoName(e.target.value)} required /></label><label>Local repository root<input value={root} onChange={e => setRoot(e.target.value)} placeholder="/workspace/project" required /></label><button type="submit">Register repository</button></form>
    </div>{message && <div className="notice">{message}</div>}
  </section>
}
