# React editor

Stage 2 implements the Windows-first writing workspace in React + TypeScript + Vite.

## Run

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/`. Vite proxies `/api` and `/health` to the local FastAPI
service at `http://127.0.0.1:8000`. When the backend has no projects or is offline, the
editor opens with a local demo work and keeps edits in browser local storage until the
service is available again.

## Included in stage 2

- Three-column writing workspace: project tree, chapter editor, assistant/version panel.
- Chapter selection and loading through the existing project tree and chapter APIs.
- Local draft autosave with offline status and manual version save through operation approval.
- Word count, writing/outline mode controls, revision timeline, and assistant quick actions.
- Responsive narrow-window layout for development and later Tauri WebView embedding.
- Real Provider/SSE assistant path for non-demo projects, including streaming deltas, cancel,
  reconnect cursor, and operation approval; demo projects keep the local fallback.

Build a production bundle with `npm run build`; output is written to `frontend/dist/`.
