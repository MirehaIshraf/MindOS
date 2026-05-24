# MindOS Frontend

This is the React frontend foundation for MindOS, a local-first personal AI operating system for developers.

## Current Scope

This step includes:

- Vite, React, TypeScript, and TailwindCSS setup
- Main dark application layout
- Fixed sidebar and top bar
- React Router routes for the future product areas
- Backend health status polling
- Zustand app state
- Axios API service placeholders
- Shared UI components and placeholder pages

## Not Implemented Yet

The frontend does not implement real chat, search, ingestion, task execution, connectors, playbooks, or settings behavior yet.

Search is treated as an internal retrieval capability. The main user-facing experience is Chat. The Memory page is for inspecting captured knowledge.

## Install

```bash
npm install
```

## Run

```bash
npm run dev
```

## Backend Requirement

The health indicator checks:

```text
http://localhost:8000/health
```

Start the backend first if you want to see `Backend online`. If the backend is not running, the UI should show `Backend offline`.

## Test Checklist

- `npm install` completes successfully
- `npm run dev` starts Vite on `http://127.0.0.1:5173`
- `/` redirects to `/chat`
- `/memory` renders the Memory page
- Sidebar navigation highlights the active route
- Each placeholder page renders its title and description
- Top bar shows backend online/offline state
- TypeScript build passes with `npm run build`
