# Frontend Guide

React single-page application for submitting lecture-to-notes pipeline jobs, monitoring their progress in real time, and viewing the final Markdown/PDF output.

## 1. Tech Stack

| Dependency                   | Version | Role                                         |
| ---------------------------- | ------- | -------------------------------------------- |
| React                        | 19.2    | UI framework                                 |
| TypeScript                   | 5.9     | Static typing                                |
| Vite                         | 7.3     | Dev server and production bundler             |
| Tailwind CSS                 | 4.1     | Utility-first styling                        |
| @tailwindcss/typography      | 0.5     | `prose` classes for rendered Markdown         |
| @tailwindcss/vite            | 4.1     | Vite plugin for Tailwind (replaces PostCSS)  |
| react-router-dom             | 7.13    | Client-side routing                          |
| react-markdown               | 10.1    | Renders Markdown output as HTML              |
| @vitejs/plugin-react         | 5.1     | React Fast Refresh for Vite                  |
| ESLint + eslint-plugin-react-hooks + eslint-plugin-react-refresh | 9.39 | Linting |

## 2. Getting Started

### Prerequisites

- **Node.js** (LTS recommended)
- **Backend API** running on `http://localhost:8000` -- the frontend talks to `/api/v1/*` on that host

### Install and run

```bash
cd frontend
npm install
npm run dev          # starts Vite dev server on http://localhost:5173
```

The dev server does **not** proxy API requests. The API base URL is hard-coded in `src/api/client.ts` as `http://localhost:8000/api/v1`. Make sure the backend is running before using the UI.

### Other scripts

| Script              | Command              | Description                              |
| ------------------- | -------------------- | ---------------------------------------- |
| `npm run dev`       | `vite`               | Start Vite dev server (port 5173)        |
| `npm run build`     | `tsc -b && vite build` | Type-check then produce production build |
| `npm run lint`      | `eslint .`           | Run ESLint across the project            |
| `npm run preview`   | `vite preview`       | Serve the production build locally       |

## 3. Project Structure

```
frontend/
  src/
    main.tsx                    # ReactDOM entry point (StrictMode wrapper)
    App.tsx                     # BrowserRouter + route definitions
    index.css                   # Tailwind imports + global styles

    api/
      client.ts                 # apiFetch() generic fetch wrapper, ApiError, apiFileUrl()
      jobs.ts                   # API functions: createJob, listJobs, getJob, getJobOutput, cancelJob, browseAudio, searchAudio, getTopics
      types.ts                  # TypeScript interfaces matching the Python backend models

    hooks/
      useJobs.ts                # Polls job list every 3 s while any job is active
      useJobDetail.ts           # Polls a single job every 3 s while it is queued/running
      useJobOutput.ts           # Fetches completed job output (book + PDF metadata)

    components/
      Layout.tsx                # App shell: header with nav link and API health indicator
      JobSubmitForm.tsx         # Job creation form (URLs, title, prompt, advanced options)
      AudioBrowser.tsx          # Modal: browse/search ISKCON Desire Tree audio library
      TopicBrowser.tsx          # Browse-by-topic view inside the audio browser (scriptures, festivals, themes, practices)
      TopicTreeMap.tsx          # Squarified treemap visualisation of audio library folders
      JobList.tsx               # Sorted list of all jobs
      JobCard.tsx               # Single job row: title, URL count, status badge, timestamps
      StepProgress.tsx          # Horizontal stepper showing pipeline stages
      StatusBadge.tsx           # Colored pill badge for job status (queued/running/completed/failed)
      OutputViewer.tsx          # Stats grid, file download links, rendered Markdown preview
      ErrorDisplay.tsx          # Red error box

    pages/
      DashboardPage.tsx         # Home page: submit form + job list, handles resubmit state
      JobDetailPage.tsx         # Single job view: progress, log, URLs, output, cancel/resubmit

    utils.ts                    # timeAgo() and formatDuration() helpers
    assets/                     # Static assets (images, etc.)
```

## 4. Key Components

### Layout (`Layout.tsx`)

Top-level wrapper rendered around every page. Provides:
- A header with a "Lecture to Notes" link back to `/`
- A live API health indicator (green/red dot) that pings `GET /health` every 15 seconds

### JobSubmitForm (`JobSubmitForm.tsx`)

The main form for creating pipeline jobs. Fields:

- **Audio URLs** -- textarea accepting one URL per line (or comma-separated). Supports direct paste or selecting files via the `AudioBrowser` modal.
- **Title** -- optional title for the output book.
- **Prompt** -- optional custom instructions for LLM enrichment.
- **Advanced Options** (collapsible panel):
  - Speaker name
  - Whisper model (`tiny`, `base`, `small`, `medium`, `large-v3`)
  - Whisper backend (`faster-whisper` or `whisper.cpp`)
  - Enrichment mode (`auto`, `lecture-centric`, `verse-centric`)
  - Toggles for speaker diarization, LLM enrichment, PDF generation, VAD filter

Accepts `initialValues` prop to pre-fill the form when a user clicks "Resubmit" from a completed or failed job.

### AudioBrowser (`AudioBrowser.tsx`)

Full-screen modal for browsing the ISKCON Desire Tree audio library (`audio.iskcondesiretree.com`). Features:

- **Browse tab** -- navigate the directory tree with breadcrumbs, switch between list view and treemap view
- **Topics tab** -- browse by curated topics (delegates to `TopicBrowser`)
- **Search** -- debounced search (500 ms) with grouped results, collapsible groups
- **File selection** -- toggle individual audio files, then "Add to Job" appends selected URLs to the form textarea

### TopicBrowser (`TopicBrowser.tsx`)

Renders curated topic categories (scriptures, festivals, themes, practices) as colored pill buttons. Clicking a topic searches for matching audio and displays grouped results. Each category has a distinct color scheme defined in `CATEGORY_STYLES`.

### TopicTreeMap (`TopicTreeMap.tsx`)

A squarified treemap layout that visualises directory entries as proportionally-sized rectangles. Each folder is sized by its item count. Color is determined by keyword matching (Prabhupada, Swami, Prabhuji, Mataji, etc.). Clicking a rectangle navigates into that folder.

### JobList (`JobList.tsx`)

Renders an array of `JobSummary` objects as a list of `JobCard` components, sorted newest-first by `created_at`.

### JobCard (`JobCard.tsx`)

A clickable card linking to `/jobs/:jobId`. Shows the job title, URL count, current step detail, status badge, relative timestamp, and elapsed duration.

### StepProgress (`StepProgress.tsx`)

A horizontal stepper that renders the seven pipeline stages:

1. Download
2. Transcribe
3. Enrich
4. Validate
5. Compile
6. PDF
7. Done

Completed steps show a green checkmark, the active step pulses blue, and a failed step shows red. Connected by horizontal lines between the circles.

### StatusBadge (`StatusBadge.tsx`)

A small colored pill that displays a `JobStatus` value:
- `queued` -- gray
- `running` -- blue with pulse animation
- `completed` -- green
- `failed` -- red

### OutputViewer (`OutputViewer.tsx`)

Displayed on the job detail page when a job completes. Shows:
- A stats grid (chapters, words, verses referenced, PDF pages)
- Download links for each output file (Markdown, PDF) using `apiFileUrl()`
- The full book Markdown rendered via `react-markdown` inside a `prose prose-slate` container

### ErrorDisplay (`ErrorDisplay.tsx`)

A simple red-bordered box with an "Error" heading and a message string. Used on both the dashboard and job detail page.

## 5. API Client

### Base client (`api/client.ts`)

All HTTP communication goes through a single generic function:

```typescript
const API_BASE = "http://localhost:8000/api/v1";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T>
```

- Prepends `API_BASE` to every path
- Sets `Content-Type: application/json` by default
- On non-OK responses, parses the body for a `detail` field and throws an `ApiError` with the HTTP status code
- Returns parsed JSON typed as `T`

A helper `apiFileUrl(jobId, filename)` builds direct download URLs for output files.

### API functions (`api/jobs.ts`)

| Function        | Method | Endpoint                          | Description                          |
| --------------- | ------ | --------------------------------- | ------------------------------------ |
| `checkHealth`   | GET    | `/health`                         | Backend health check                 |
| `createJob`     | POST   | `/jobs`                           | Submit a new pipeline job            |
| `listJobs`      | GET    | `/jobs`                           | List all jobs (summary)              |
| `getJob`        | GET    | `/jobs/:id`                       | Full job detail                      |
| `getJobOutput`  | GET    | `/jobs/:id/output`                | Book + PDF output for completed job  |
| `cancelJob`     | POST   | `/jobs/:id/cancel`                | Cancel a running/queued job          |
| `browseAudio`   | GET    | `/browse?path=...`                | Browse ISKCON Desire Tree directory  |
| `searchAudio`   | GET    | `/browse/search?q=...`            | Search audio library by title        |
| `getTopics`     | GET    | `/browse/topics`                  | Fetch topic taxonomy                 |

### Polling pattern

The frontend uses `setInterval`-based polling rather than WebSockets:

- **`useJobs`** -- On mount, fetches the full job list. Sets up a 3-second interval that only calls `listJobs()` if at least one job is `queued` or `running`. This avoids unnecessary requests when all jobs are finished.
- **`useJobDetail`** -- Fetches the job once on mount. If the job is `queued` or `running`, starts a 3-second polling interval. The interval is cleared automatically when the job reaches a terminal state (`completed` or `failed`).
- **`useJobOutput`** -- Fetches the output exactly once when `isCompleted` becomes `true`. No polling.

### TypeScript types (`api/types.ts`)

All interfaces mirror the backend Python models:

- `JobStatus` -- `"queued" | "running" | "completed" | "failed"`
- `PipelineStep` -- `"pending" | "downloading" | "transcribing" | "enriching" | "validating" | "compiling" | "pdf_generating" | "completed" | "failed"`
- `JobCreateRequest`, `JobCreateResponse`, `JobSummary`, `JobDetail`
- `BookOutput`, `Chapter`, `CompilationReport`, `PDFOutput`, `JobOutputResponse`
- `BrowseEntry`, `BrowseResponse`, `SearchEntry`, `SearchGroup`, `SearchResponse`
- `TopicEntry`, `TopicCategory`, `TopicTaxonomyResponse`

## 6. State Management

The app uses **React built-in hooks only** -- no Redux, Zustand, or other external state library.

| Hook                  | Where used             | Purpose                                      |
| --------------------- | ---------------------- | -------------------------------------------- |
| `useState`            | Everywhere             | Local component state                        |
| `useEffect`           | Hooks, Layout          | Data fetching, polling intervals, side effects |
| `useCallback`         | useJobs, AudioBrowser  | Stable function references for intervals     |
| `useRef`              | useJobs, AudioBrowser  | Mutable refs for latest state in intervals, DOM refs |
| `useMemo`             | TopicTreeMap           | Memoised treemap layout calculation          |
| `useParams`           | JobDetailPage          | Extract `:jobId` from URL                    |
| `useLocation`         | DashboardPage          | Read router state for resubmit data          |
| `useNavigate`         | DashboardPage, JobDetailPage | Programmatic navigation, clearing router state |

State flows top-down via props. The `DashboardPage` owns the job list state (via `useJobs`) and passes a `refresh` callback to `JobSubmitForm` so newly created jobs appear immediately.

Resubmit workflow: `JobDetailPage` navigates to `/` with `location.state.resubmit` containing the job's URLs, title, and config. `DashboardPage` reads this state and passes it as `initialValues` to `JobSubmitForm`.

## 7. Routing

Routing is handled by `react-router-dom` v7 with `BrowserRouter`. There are two routes:

| Path            | Page              | Description                                   |
| --------------- | ----------------- | --------------------------------------------- |
| `/`             | `DashboardPage`   | Job submission form + list of all jobs         |
| `/jobs/:jobId`  | `JobDetailPage`   | Single job: progress, log, URLs, output viewer |

The `Layout` component wraps both routes and provides the persistent header.

Navigation between pages:
- `JobCard` links to `/jobs/:jobId`
- `JobDetailPage` has a "Back to dashboard" link to `/`
- The "Resubmit" button on `JobDetailPage` navigates to `/` with state

## 8. Styling

### Tailwind CSS 4.1

Tailwind is loaded via the `@tailwindcss/vite` plugin (not PostCSS). The entry point is `src/index.css`:

```css
@import "tailwindcss";
@plugin "@tailwindcss/typography";
```

All styling uses Tailwind utility classes directly in JSX. There are no CSS modules or styled-components.

### Key patterns

- **Layout**: `min-h-screen bg-gray-50` on the root, `max-w-6xl mx-auto px-6` for content width
- **Cards**: `rounded-lg border border-gray-200 bg-white p-6 shadow-sm`
- **Forms**: Standard border/ring focus styles (`focus:border-blue-500 focus:ring-1 focus:ring-blue-500`)
- **Status colors**: Gray for queued, blue for running, green for completed, red for failed
- **Animations**: `animate-pulse` on the active pipeline step and running status badge, `animate-spin` on loading spinners

### Typography plugin

The `@tailwindcss/typography` plugin provides `prose` classes used in `OutputViewer` to render the final Markdown book:

```tsx
<div className="prose prose-slate max-w-none">
  <Markdown>{book.full_book_markdown}</Markdown>
</div>
```

This gives the rendered Markdown proper heading sizes, paragraph spacing, list styles, blockquote formatting, and code block styling without any manual CSS.

## 9. Building for Production

```bash
cd frontend
npm run build
```

This runs `tsc -b` (type-checking) followed by `vite build`. Output goes to `frontend/dist/`.

To preview the production build locally:

```bash
npm run preview
```

The `dist/` directory contains static files (HTML, JS, CSS) that can be served by any static file server or embedded behind the backend's static file serving.

## 10. Adding New Features

### Adding a new component

1. Create `frontend/src/components/MyComponent.tsx`
2. Export a named function component
3. Import and use it in a page or another component
4. Follow the existing pattern: props interface at the top, Tailwind classes for styling

### Adding a new page/route

1. Create `frontend/src/pages/MyPage.tsx`
2. Add a `<Route>` in `App.tsx`:
   ```tsx
   <Route path="/my-path" element={<MyPage />} />
   ```
3. All routes render inside the `<Layout>` wrapper automatically

### Adding a new API endpoint

1. Add the TypeScript interface to `frontend/src/api/types.ts` -- keep these in sync with the backend Python models
2. Add the API function to `frontend/src/api/jobs.ts`:
   ```typescript
   export const myEndpoint = (param: string) =>
     apiFetch<MyResponse>(`/my-endpoint/${param}`);
   ```
3. If the endpoint needs polling, create a custom hook in `frontend/src/hooks/` following the pattern in `useJobDetail.ts`

### Adding a new custom hook

1. Create `frontend/src/hooks/useMyHook.ts`
2. Follow the `{ data, loading, error }` return pattern used by the existing hooks
3. If polling is needed, use `setInterval` inside a `useEffect` and clean up with `clearInterval` in the return function
4. Gate polling on an active condition to avoid unnecessary requests when data is settled

### Type safety

All API responses are typed end-to-end. The `types.ts` file defines the contract. When the backend adds a new field, add it to the corresponding interface in `types.ts` and TypeScript will flag all places that need updating. The `tsc -b` step in `npm run build` ensures no type errors ship to production.
