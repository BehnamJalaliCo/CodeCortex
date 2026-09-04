# Discovery Manual Steps

These are repository settings that cannot be changed by the current automation connection. All code/assets needed for them are already prepared in this branch.

## 1. Repository About metadata

Open the CodeCortex repository page and click the **gear icon** next to **About**.

Set description to:

> Open-source context intelligence engine for AI coding agents — repository graph, precise code navigation, MCP, impact analysis, memory, and guarded edits.

Set website to:

`https://behnamjalalico.github.io/CodeCortex/`

Add these topics (GitHub supports up to 20):

- `coding-agents`
- `ai-agents`
- `agentic-ai`
- `mcp`
- `model-context-protocol`
- `code-intelligence`
- `context-engine`
- `developer-tools`
- `repository-analysis`
- `code-search`
- `semantic-search`
- `knowledge-graph`
- `static-analysis`
- `refactoring`
- `software-engineering`
- `llm`
- `python`
- `devtools`

## 2. GitHub Discussions

Go to repository **Settings → General → Features** and enable **Discussions**.

Recommended categories:

- Announcements
- Q&A
- Ideas
- Show and tell

After enabling it, replace any temporary issue-only community CTA with the repository Discussions URL.

## 3. Social preview

The source asset is:

`docs/assets/social-preview.svg`

Export it as a 1280×640 PNG, then open repository **Settings → General → Social preview** and upload the PNG.

The preview intentionally contains no partner logos, fake adoption metrics, or unverified claims.

## 4. Glama submission

Submit the public CodeCortex repository to Glama using the canonical metadata in `docs/DISCOVERY_SUBMISSIONS.md`.

## 5. Curated awesome-list PR

Open one PR to the selected maintained MCP awesome list using the exact entry in `docs/DISCOVERY_SUBMISSIONS.md`.

Do not submit duplicate PRs to multiple near-identical forks.

## Completion rule

After these settings are applied, verify the public repository page in a logged-out browser:

- About shows the new description, website, and topics.
- Discussions tab is visible.
- Social preview appears when the repository URL is shared.
- Documentation website opens.
- Latest release and PyPI links resolve.
