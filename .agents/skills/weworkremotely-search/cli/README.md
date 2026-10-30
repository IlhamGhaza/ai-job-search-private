# weworkremotely-search CLI

We Work Remotely Search - zero runtime dependencies (plain `bun` + `fetch`).

```bash
bun install          # dev types only
bun run typecheck
bun test             # offline: fixtures and a local mock server, no live calls
bun run src/cli.ts --help
```

`src/helpers.ts` is the shared portal kit (HTTP backoff, output hygiene, the job
record, output formats, argument parsing); it is an identical copy in every
portal added for the global search. See `../SKILL.md` for usage and
`../url-reference.md` for endpoints.
