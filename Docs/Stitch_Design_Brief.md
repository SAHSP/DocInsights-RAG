# RAG Pipeline — Stitch Design Brief

> **Purpose**: This document is the design prompt for Stitch. It describes every page, layout, component, interaction, color, and style required so Stitch can generate production-quality HTML, CSS (with libraries/frameworks), and JS prototypes.

---

## Global Design System

### Theme
- **Mode**: Dark mode primary (default); light mode toggle optional
- **Background**: `#0f0f13` (near-black, slightly warm)
- **Surface / Card**: `#1a1a24` with `1px` border `#2a2a38`
- **Sidebar**: `#13131c`
- **Font**: `Inter` from Google Fonts — weights 400, 500, 600, 700
- **Border radius**: `12px` for cards, `8px` for buttons/inputs, `6px` for badges

### Color Palette

| Token | Hex | Usage |
|---|---|---|
| `--color-primary` | `#6366f1` | Primary buttons, active nav, links |
| `--color-primary-hover` | `#4f46e5` | Button/link hover |
| `--color-accent` | `#22d3ee` | Highlights, active states, icons |
| `--color-success` | `#22c55e` | Indexed status, success toasts |
| `--color-warning` | `#f59e0b` | Extracting/Chunking status, warnings |
| `--color-danger` | `#ef4444` | Failed status, errors |
| `--color-muted` | `#6b7280` | Secondary text, disabled |
| `--color-border` | `#2a2a38` | Card/input borders |
| `--color-text` | `#e5e7eb` | Primary text |
| `--color-text-secondary` | `#9ca3af` | Secondary/helper text |

### Status Badge Colors (Pipeline)

| Status | Color |
|---|---|
| `pending` | gray `#6b7280` |
| `extracting` | amber `#f59e0b` |
| `chunking` | blue `#3b82f6` |
| `embedding` | purple `#a855f7` |
| `indexed` | green `#22c55e` |
| `failed` | red `#ef4444` |

Status badges should be a small pill shape: colored dot + label text.

### Typography Scale
- **Page title**: 24px, 700 weight
- **Section heading**: 18px, 600 weight
- **Card title**: 15px, 600 weight
- **Body**: 14px, 400 weight
- **Small/helper**: 12px, 400 weight, muted color

### Shared Layout Shell
All pages (except Landing) share this shell:
- **Left sidebar**: 240px wide, fixed, dark background
  - App logo/name at top: `RAG` with a small database icon, styled in gradient text (indigo → cyan)
  - Navigation links with icons: Dashboard, Chat, History, Documents, Settings
  - Active link: indigo left border + indigo text + subtle bg
  - Hover: slight bg highlight
  - Bottom of sidebar: a small system health dot (green = all services OK)
- **Main content area**: fills remainder, has `24px` padding, scrollable
- **Top bar** (inside main area): breadcrumb left, right side has user avatar placeholder + notification bell icon

### CSS Libraries / Frameworks Allowed
- Use **Tailwind CSS CDN** for utility classes
- Use **Lucide Icons** (via CDN) for all icons
- Use **Chart.js** (via CDN) for any charts/graphs
- Use vanilla JS for interactions (no React needed at this stage)
- Optional: **Alpine.js** for lightweight reactivity (dropdowns, toggles, accordions)

---

## Page 1 — Landing / Dashboard (`/`)

### Purpose
Entry point. Gives team members an instant overview of the system state.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR (breadcrumb: Dashboard)           │
│           │────────────────────────────────────────────│
│           │  GREETING HERO BAR                         │
│           │  "Good morning. Here's your RAG overview." │
│           │────────────────────────────────────────────│
│           │  [STATS ROW — 4 cards]                     │
│           │────────────────────────────────────────────│
│           │  [HEALTH ROW]      │  [RECENT QUERIES]     │
│           │  Service status    │  Last 5 queries list  │
│           │────────────────────│───────────────────────│
│           │  [RECENT DOCUMENTS — table]                │
│           │────────────────────────────────────────────│
│           │  [QUICK ACTIONS — 2 buttons]               │
└──────────────────────────────────────────────────────┘
```

### Components

#### Hero Bar
- Full-width banner (subtle gradient: indigo-to-transparent left edge)
- Large greeting text: `"Good morning 👋"` (time-aware: morning/afternoon/evening)
- Subtitle: `"Here's what's happening in your RAG pipeline."`
- Current date/time shown on right side

#### Stats Cards Row (4 cards, equal width)
Card design: dark surface, colored icon top-left, large number, label below

| Card | Icon | Color |
|---|---|---|
| Total Documents | FileText | indigo |
| Indexed Documents | CheckCircle | green |
| Queries Today | MessageSquare | cyan |
| Failed Ingestions | AlertTriangle | red |

Each card shows:
- Icon (24px, colored)
- Big number (32px bold) — placeholder: `0`
- Label (12px muted)
- Small trend indicator: ↑/↓ with percentage change in lighter color (placeholder)

#### Service Health Panel (left half of middle row)
- Title: "Service Health"
- List of services with status indicator dots:
  - `API Server` — green dot + "Online"
  - `Celery Worker` — green dot + "Online"
  - `MinIO` — green dot + "Online"
  - `PostgreSQL` — green dot + "Online"
  - `OpenSearch` — green dot + "Online"
  - `Redis` — green dot + "Online"
- Use pulsing animation on green dots to feel "alive"
- If status is "Offline" → red dot, static

#### Recent Queries Panel (right half of middle row)
- Title: "Recent Queries"
- List of 5 rows:
  - Query text (truncated at ~60 chars)
  - Timestamp (relative: "2 min ago")
  - Search mode badge: `Semantic` / `Keyword` / `Hybrid` (pill badge, small)
- Empty state: icon + "No queries yet. Start asking questions."
- "View all" link → navigates to `/history`

#### Recent Documents Table (below middle row)
- Title: "Recent Documents"
- Columns: Filename | Type | Uploaded | Status
- 5 rows max
- Status column: colored status badge pill
- Row hover: subtle highlight
- "View all" link → navigates to `/documents`

#### Quick Actions Row (bottom)
- Two large buttons side by side:
  - `Upload Document` (primary, indigo) → triggers upload modal
  - `Start Querying` (secondary, outlined) → navigates to `/chat`

---

## Page 2 — Chat (`/chat`)

### Purpose
Primary page. Users submit natural language queries and receive LLM-generated answers with source citations.

### Layout

```
┌────────────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR                                        │
│           │──────────────────────────────────────────────── │
│           │  CHAT TOOLBAR (mode toggle + doc scope picker)  │
│           │──────────────────────────────────────────────── │
│           │                                                  │
│           │         CHAT MESSAGE THREAD                      │
│           │         (scrollable area)                        │
│           │                                                  │
│           │──────────────────────────────────────────────── │
│           │  QUERY INPUT BAR (sticky bottom)                 │
└────────────────────────────────────────────────────────────┘
```

### Components

#### Chat Toolbar (top bar inside main area)
- **Search Mode Toggle**: three-tab toggle pill
  - `Keyword` | `Semantic` | `Hybrid`
  - Selected tab: indigo background, white text
  - Unselected: muted text, transparent bg
- **Document Scope Selector**: dropdown
  - Default: "All Documents"
  - Options: list of indexed documents (by filename)
  - Styled as a custom select with a `ChevronDown` icon

#### Chat Thread Area
- Scrollable, takes up most of the vertical space
- Empty state (no messages): centered illustration + text
  - Title: `"Ask anything about your documents"`
  - Subtitle: `"Choose a search mode, select a document scope, and start typing."`
  - Three example query chips below (clickable to prefill input):
    - `"Summarize the key findings"`
    - `"What are the main risks mentioned?"`
    - `"List all action items"`

#### Message Bubbles

**User Query Bubble** (right-aligned):
- Indigo background pill/bubble
- White text
- Small timestamp below, right-aligned
- User avatar placeholder on far right (circle, initials)

**AI Answer Bubble** (left-aligned):
- Dark card surface, border `--color-border`
- RAG logo/icon top-left of bubble
- Answer text: rendered as markdown (use `marked.js` CDN for markdown rendering)
- Below answer text: **Citations Section**
  - Title: "Sources" with a `BookOpen` icon
  - Each citation: horizontal pill card showing:
    - File icon + filename
    - Page number badge
    - Short text snippet (truncated, 2-3 lines)
    - On hover: expand snippet slightly
  - Citations expand into accordions if more than 3
- **Loading state**: three animated typing dots while waiting for response

#### Query Input Bar (sticky bottom)
- Full-width input bar:
  - Text input: `"Ask a question about your documents..."` placeholder
  - Left icon: `Search` icon (indigo)
  - Right side: `Send` button (indigo, circular icon button)
  - Also: paperclip icon (placeholder for future file attach)
- On focus: input border glows indigo
- Press Enter or click Send → submits query
- While loading: input disabled, send button shows spinner

---

## Page 3 — Query History (`/history`)

### Purpose
Full log of all past queries across all sessions. Searchable and filterable.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR (breadcrumb: History)               │
│           │──────────────────────────────────────────────│
│           │  FILTER BAR                                  │
│           │──────────────────────────────────────────────│
│           │  HISTORY TABLE (paginated)                   │
│           │  [expanded row: full answer + citations]     │
└──────────────────────────────────────────────────────────┘
```

### Components

#### Filter Bar
- Row of filter controls:
  - `Search` text input — filter by query keyword
  - `Date Range` — from/to date pickers (simple inputs type=date)
  - `Document` — dropdown to filter by document used
  - `Mode` — dropdown: All | Keyword | Semantic | Hybrid
  - `Status` — dropdown: All | Answered | Failed
  - `Clear Filters` link

#### History Table
- Columns:
  - `#` (row number)
  - `Query` (truncated, ~80 chars, bold)
  - `Document Scope` (filename or "All Documents")
  - `Mode` (Keyword/Semantic/Hybrid badge)
  - `Time` (relative + absolute on hover tooltip)
  - `Status` (Answered = green badge, Failed = red badge)
  - `Actions` (two icon buttons: `Eye` = View, `RotateCcw` = Re-run)
- Row hover: subtle row highlight
- Click anywhere on row → expands accordion below that row showing:
  - Full answer text (markdown rendered)
  - Citations list (same style as Chat page)
  - "Open in Chat" button → navigates to `/chat` with this query pre-filled
- Pagination at bottom: `← Previous | Page 1 of N | Next →`
- Empty state: icon + "No query history yet."

---

## Page 4 — Document Library (`/documents`)

### Purpose
Manage all uploaded documents and their pipeline status.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR                                     │
│           │─────────────────────────────────────────────│
│           │  PAGE HEADER: "Documents"  [Upload Button]   │
│           │─────────────────────────────────────────────│
│           │  FILTER BAR                                  │
│           │─────────────────────────────────────────────│
│           │  DOCUMENT TABLE                              │
│           │  (paginated)                                 │
└──────────────────────────────────────────────────────────┘
│  UPLOAD MODAL (overlay, hidden by default)               │
```

### Components

#### Page Header
- Left: "Documents" title (24px bold)
- Right: `Upload Document` button (indigo, `+` icon left, `Upload` text)

#### Filter Bar
- `Search` text input (filter by filename)
- `Type` dropdown: All | PDF | DOCX
- `Status` dropdown: All | Pending | Extracting | Chunking | Embedding | Indexed | Failed
- `Sort By` dropdown: Newest First | Oldest First | Name A-Z

#### Document Table
- Columns:
  - Checkbox (for batch select — placeholder)
  - `File` (file icon matching type + filename in bold, mime/type below in muted)
  - `Size` (file size in KB/MB)
  - `Uploaded` (relative date)
  - `Status` (colored badge pill — see Global Status Colors)
  - `Actions`:
    - `Eye` icon → navigate to `/documents/:id`
    - `MessageSquare` icon → navigate to `/chat` with this doc pre-selected
    - `Trash2` icon → delete confirmation (show inline confirm or small modal)
- Row hover: subtle highlight
- Status badges: pulsing animation if status is `extracting`, `chunking`, or `embedding` (to indicate in-progress)
- Pagination at bottom
- Empty state (no documents): large centered illustration + "No documents uploaded yet." + `Upload your first document` button

#### Upload Modal
Triggered by `Upload Document` button. Full-screen overlay, centered modal card (max 520px wide).

**Modal structure:**
- Close `X` button top-right
- Title: "Upload Document"
- Subtitle: "Supported formats: PDF, DOCX"
- **Drop zone**: large dashed-border area
  - Icon: `UploadCloud` (48px, indigo)
  - Text: `"Drag & drop your file here"` + `"or click to browse"`
  - On hover: border turns solid indigo, background tints lightly
  - Accepted file types: `.pdf`, `.docx`
- **Selected file state** (after file picked):
  - File icon + filename + file size
  - Remove `×` button to clear selection
- **Upload button** (full width, indigo): `"Upload & Process"` — disabled until file selected
- **Progress state**: progress bar (indigo) + percentage text
- **Success state**: green checkmark icon + "File uploaded successfully. Processing has started." + Close button
- **Error state**: red error icon + error message

---

## Page 5 — Document Detail (`/documents/:id`)

### Purpose
Deep view of a single document — metadata, pipeline progress, and chunk inspection.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR (breadcrumb: Documents > filename)  │
│           │─────────────────────────────────────────────│
│           │  DOCUMENT HEADER (meta + actions)           │
│           │─────────────────────────────────────────────│
│           │  PIPELINE STATUS TRACKER                    │
│           │─────────────────────────────────────────────│
│           │  TABS: [Chunks] [Metadata]                  │
│           │  TAB CONTENT AREA                           │
└──────────────────────────────────────────────────────────┘
```

### Components

#### Document Header
- Left:
  - Large file icon (PDF or DOCX, colored)
  - Filename (20px bold)
  - Below: muted metadata row: `PDF · 2.3 MB · Uploaded 2 days ago`
- Right:
  - `Query this Document` button (indigo, `MessageSquare` icon)
  - `Download` icon button
  - `Delete` icon button (red on hover)

#### Pipeline Status Tracker
Horizontal stepper showing pipeline stages:

```
[Uploaded] → [Extracting] → [Chunking] → [Embedding] → [Indexed]
```

- Each step: circle icon + label below
- Completed step: filled indigo circle with `Check` icon
- Current step: pulsing indigo ring (animated)
- Pending step: gray empty circle
- Failed step: red circle with `X` icon
- Connecting lines between steps: gray (completed = indigo fill)

#### Tabs

**Tab 1 — Chunks**
- Shows all parent chunks for this document
- Table columns:
  - `#` (chunk index)
  - `Page` (page number)
  - `Type` (badge: text | table | ocr | image_caption)
  - `Preview` (first 100 chars of chunk_text, truncated)
  - `Child Chunks` (count of child chunks derived from this parent)
- Click row → expand to show full chunk text below row
- Pagination if > 20 chunks

**Tab 2 — Metadata**
- Key-value grid layout:
  - `File ID`: UUID
  - `Filename`: original name
  - `File Type`: PDF/DOCX
  - `MinIO Path`: `raw-documents/{id}/filename.pdf`
  - `Upload Date`: timestamp
  - `Last Updated`: timestamp
  - `Total Parent Chunks`: count
  - `Total Child Chunks`: count
  - `Status`: current pipeline status badge

---

## Page 6 — Settings (`/settings`)

### Purpose
System configuration for LLM, search, and infrastructure settings.

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  SIDEBAR  │  TOP BAR (breadcrumb: Settings)              │
│           │─────────────────────────────────────────────│
│           │  LEFT: Settings Nav   │  RIGHT: Panel       │
│           │  (vertical tabs)      │  (form content)     │
└──────────────────────────────────────────────────────────┘
```

### Settings Navigation (left side, vertical)
- `Cpu` icon — LLM Provider
- `Cpu` icon — Embedding Model
- `Search` icon — Search Defaults
- `Database` icon — Cache & Storage
- `Activity` icon — System Info

### Settings Panels

#### LLM Provider Panel
- Dropdown: `Provider` — OpenAI | Azure | Anthropic | Ollama (self-hosted)
- Text input: `API Key` (password type, show/hide toggle)
- Text input: `Model Name` (e.g. `gpt-4o`, `claude-3-opus`)
- Text input: `Base URL` (shown only if Ollama selected)
- `Save` button (indigo)

#### Embedding Model Panel
- Read-only display: Current Model — `BAAI/bge-large-en-v1.5`
- Dropdown: swap model (list of compatible models — placeholder options)
- Info callout box: "Changing the embedding model requires re-indexing all documents."
- `Apply` button

#### Search Defaults Panel
- Toggle group: Default Search Mode — `Keyword` | `Semantic` | `Hybrid`
- Slider: Top-K Results (range 5–50, default 20)
- Slider: Reranker Top-N (range 1–10, default 5)
- `Save` button

#### Cache & Storage Panel
- Toggle: Enable Query Result Cache (Redis) — ON/OFF
- Text: "Cache TTL: 3600 seconds"
- `Clear Cache` button (danger, outlined red)
- Info text: "Clearing cache will force all queries to re-run."

#### System Info Panel
- Read-only grid:
  - API Version: `v1.0.0`
  - Environment: `development`
  - Services health summary (mini status list same as dashboard)

---

## Shared Components Specification

### Sidebar Navigation
```
┌─────────────────────┐
│  🔷 RAG             │  ← App name, gradient text
│─────────────────────│
│  ⊞  Dashboard       │
│  💬 Chat            │
│  🕐 History         │
│  📄 Documents       │
│  ⚙️  Settings       │
│─────────────────────│
│  ● All systems OK   │  ← health indicator (bottom)
└─────────────────────┘
```
- Active page: indigo `3px` left border, indigo text, slight bg highlight
- Icons: Lucide icons (18px)

### Toast Notifications
- Position: top-right, stacked
- Types: success (green), error (red), info (indigo), warning (amber)
- Auto-dismiss after 4 seconds
- Slide-in animation from right

### Empty States
Always use: centered icon (48px, muted) + bold title + muted subtitle + optional action button

### Loading States
- Skeleton loaders for tables/lists (animated shimmer, dark gray bars)
- Spinner for buttons (small, white, inline)
- Full overlay spinner for page-level loading

---

## Interactions & Animations

| Interaction | Behavior |
|---|---|
| Button hover | Scale 1.02, shadow deepen, 150ms ease |
| Card hover | Border color → indigo, slight lift shadow, 200ms |
| Sidebar link hover | Bg tint, icon color → indigo, 150ms |
| Modal open | Fade in overlay + slide-up card, 250ms |
| Toast appear | Slide in from right, 300ms |
| Status badge pulse | Keyframe loop on in-progress statuses |
| Input focus | Indigo glow ring (box-shadow), 150ms |
| Accordion expand | Smooth max-height transition, 250ms |
| Chat bubble appear | Fade in + slight slide-up, 200ms stagger |

---

## Responsive Behavior
- Designed for **desktop-first** (1280px+), internal tool
- Sidebar collapses to icon-only at < 1024px (show icons, hide labels)
- Tables scroll horizontally on smaller screens
- Modals are full-screen on mobile

---

## File Naming Convention for Stitch Output

When Stitch generates pages, name output files:
- `index.html` → Landing / Dashboard
- `chat.html` → Chat
- `history.html` → Query History
- `documents.html` → Document Library
- `document-detail.html` → Document Detail
- `settings.html` → Settings

Each HTML file should:
1. Include all CSS inline or in `<style>` tags (self-contained)
2. Link CDN libraries in `<head>`
3. Include vanilla JS at bottom of `<body>`
4. Use placeholder/mock data (no real API calls needed at this stage)
5. Have consistent sidebar + top bar across all pages
