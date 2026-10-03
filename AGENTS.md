# Graphify Agent Instructions

Maintain a Graphify knowledge graph for this workspace.

## Setup and freshness

- If `graphify-out/` is absent, build the graph immediately with `graphify .`.
- If `graphify-out/graph.json` is absent, empty, or stale after source files have been added, run `graphify update .`.
- Rebuild with `graphify update .` after five or more changed files, a branch merge or pull, an explicit user request, deleted or moved files referenced by Graphify, or when the graph is over four hours old while coding has occurred.
- Do not rebuild for one or two small edits when the graph is fresh.

## Activity signaling

Before **every** Graphify command, signal activity. On Windows run:

```powershell
New-Item -ItemType Directory -Force -Path graphify-out | Out-Null
New-Item -ItemType File -Force -Path graphify-out/.graphify-activity | Out-Null
```

For long builds, tell the user that updating or building the knowledge graph may take up to two minutes.

## Command selection

- Use `graphify query "..."` for architecture, dependencies, and high-level flow questions.
- Use `graphify explain <node_id>` for a focused component.
- Use `graphify path <nodeA> <nodeB>` to trace relationships.
- Use direct reads and search for line-level syntax or implementation questions.
- If a query returns empty, verify `graphify-out/graph.json`, update the graph, and retry with specific component names.

## Generated state

`graphify-out/` is generated per-machine state. Keep it ignored by Git and never commit it.