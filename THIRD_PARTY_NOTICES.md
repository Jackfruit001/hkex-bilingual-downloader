# Third-party notices

Runtime dependencies are permissive (MIT, BSD, Apache-2.0, ISC). Versions are pinned in
`backend/uv.lock` and `frontend/package-lock.json`.

## Backend (Python)

| Package | Licence | Use |
|---|---|---|
| FastAPI | MIT | Web framework |
| Uvicorn | BSD-3-Clause | ASGI server |
| httpx | BSD-3-Clause | HTTP client |
| Pydantic | MIT | Validated models |
| tzdata | Apache-2.0 | Time zone data for `Asia/Hong_Kong` |
| pypdf | BSD-3-Clause | Text extraction for the content check (SPEC §4.5) |
| pathvalidate | MIT | Final check that a filename is valid on Windows, macOS and Linux (SPEC §5) |

Test and lint only: pytest (MIT), pytest-asyncio (Apache-2.0), respx (BSD-3-Clause),
Hypothesis (MPL-2.0), PyYAML (MIT, golden set file), Ruff (MIT), mypy (MIT).

## Frontend

| Package | Licence | Use |
|---|---|---|
| React, React DOM | MIT | UI |
| Vite, @vitejs/plugin-react | MIT | Build |
| Tailwind CSS, @tailwindcss/vite | MIT | Styling |
| TypeScript | Apache-2.0 | Type checking |

Test only: Vitest (MIT), Playwright (Apache-2.0).

## Reused code

None so far. Open-source HKEX clients were read for reference only; see
`docs/research-notes.md` section 7.
