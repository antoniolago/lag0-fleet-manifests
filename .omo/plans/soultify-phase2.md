# Soultify — Phase 2: Spotify-like Web UI

## TL;DR

Build a Spotify-resembling SPA (Svelte 5 + Vite) embedded into the Go binary. Search, browse, play, and manage your music library through a proper web interface. Backend gets playlist/star/queue/OIDC endpoints.

---

## Context

### Current State
- Go binary with Subsonic API + OIDC auth (Phase 0 complete)
- Project at `/home/tonio/Documentos/GitHub/soultify/`
- Missing endpoints: playlists, star/unstar, play queue, OIDC auth flow
- No frontend

### Key Design Decisions
- **Svelte 5 + Vite** for the SPA (less code than React for music player state)
- **HTML5 `<audio>`** for playback (Web Audio API for gapless in Phase 3)
- **Go `//go:embed`** so the SPA is part of the binary (no separate server)
- **Pocket-ID** handles all user auth; SPA gets JWT via OIDC code flow

---

## Work Objectives

### Concrete Deliverables

**Backend (Go):**
- Playlist CRUD (DB table + 5 Subsonic endpoints)
- Star/unstar (DB column + 3 endpoints)
- Play queue persistence (DB table + 2 endpoints)
- OIDC auth flow (`/auth/login`, `/auth/callback`)
- Embedded SPA serving via `//go:embed`

**Frontend (Svelte 5 + Vite):**
- Login via Pocket-ID redirect
- Search page (artists/albums/tracks results)
- Album page (cover, tracklist, play/shuffle)
- Artist page (album grid)
- Library page (alphabetical index)
- Playlist management (create, rename, reorder, delete)
- Persistent player bar with controls + queue

### Must Have
- Spotify-dark theme
- Search returns within 2s
- Player persists across pages
- Album art from `/rest/getCoverArt`
- HTML5 `<audio>` streaming
- Login via Pocket-ID works end-to-end

### Must NOT Have
- No gapless/crossfade (Phase 3)
- No transcoding (Phase 3)
- No Home/Discover page (Phase 3)
- No recommendations (Phase 3)

---

## Verification Strategy

### Test Decision
- **Infrastructure**: soultify project (not in cluster)
- **Automated tests**: None (manual browser testing)
- **QA**: Open `http://localhost:4533` and click through the app

---

## Execution Strategy

### Waves

```
Wave 1 (Backend — 5 tasks):
├── T1: Playlist DB + CRUD
├── T2: Star/unstar
├── T3: Play queue
├── T4: OIDC auth flow
└── T5: Go embed setup

Wave 2 (SPA scaffold — 3 tasks):
├── T6: Vite + Svelte project
├── T7: API client JS module
└── T8: Svelte stores

Wave 3 (Core UI — 4 tasks, MAX PARALLEL):
├── T9: Player bar + HTML5 audio
├── T10: Search page
├── T11: Album + Artist pages
└── T12: Library page

Wave 4 (Remaining — 2 tasks):
├── T13: Playlist page + sidebar
└── T14: Auth callback + polish

Wave 5 (Integration — 1 task):
└── T15: Build + embed test
```

---

## TODOs

### Wave 1: Backend Endpoints

- [ ] 1. **Playlist DB + CRUD handlers**

  **Agent**: `deep`
  **Files**: `internal/db/schema.go`, `internal/db/playlists.go`, `pkg/subsonic/handler.go`, `pkg/subsonic/responses.go`

  **What to do**:
  - Add `playlists` and `playlist_tracks` tables to schema
  - Create `internal/db/playlists.go` with: CreatePlaylist, GetPlaylists, GetPlaylist, UpdatePlaylist, DeletePlaylist, AddTrackToPlaylist, RemoveTrackFromPlaylist, ReorderPlaylistTracks, GetPlaylistTracks
  - Add Subsonic handlers: getPlaylists, getPlaylist, createPlaylist, deletePlaylist, updatePlaylist
  - Register routes in handler.go

- [ ] 2. **Star/unstar handlers**

  **Agent**: `deep`
  **Files**: `internal/db/schema.go`, `internal/db/stars.go`, `pkg/subsonic/handler.go`

  **What to do**:
  - Add `starred` DATETIME column to tracks/albums/artists
  - DB functions: StarTrack, UnstarTrack, StarAlbum, UnstarAlbum, StarArtist, UnstarArtist, GetStarred (3 lists)
  - Subsonic handlers: star, unstar, getStarred, getStarred2

- [ ] 3. **Play queue endpoints**

  **Agent**: `unspecified-high`
  **Files**: `internal/db/schema.go`, `internal/db/queue.go`, `pkg/subsonic/handler.go`

  **What to do**:
  - Add play_queue table
  - DB: SavePlayQueue, LoadPlayQueue
  - Subsonic: savePlayQueue, loadPlayQueue

- [ ] 4. **OIDC auth redirect flow**

  **Agent**: `deep`
  **Files**: `internal/auth/handler.go`, `internal/config/config.go`, `internal/app/app.go`

  **What to do**:
  - Add `OIDC.ClientSecret` to config struct
  - Create `/auth/login` — generates Pocket-ID authorize URL with state, redirects user
  - Create `/auth/callback` — exchanges code for tokens, redirects to SPA with `#access_token=<jwt>`
  - In-memory state map with 5min TTL for CSRF protection
  - Register routes in app.go BEFORE the catch-all

- [ ] 5. **Go embed SPA setup**

  **Agent**: `unspecified-high`
  **Files**: `internal/app/app.go`

  **What to do**:
  - Add `//go:embed web/dist/*` directive
  - Register SPA file server for `/assets/` and catch-all for other paths
  - Ensure `/rest/` and `/auth/` take priority over catch-all
  - Create stub `web/dist/index.html` temporarily

### Wave 2: SPA Scaffold

- [ ] 6. **Vite + Svelte project**

  **Agent**: `unspecified-high`
  **Files**: `web/package.json`, `web/vite.config.js`, `web/src/App.svelte`

  **What to do**:
  - `npm create vite@latest web -- --template svelte`
  - Install `svelte-spa-router`
  - Config: `base: ''`, `build.outDir: 'dist'`
  - Dark theme CSS variables
  - Verify `npm run build`

- [ ] 7. **Subsonic API client**

  **Agent**: `unspecified-high`
  **Files**: `web/src/lib/subsonic.js`

  **What to do**:
  - Wrap all `/rest/` endpoints with Bearer token + JSON parsing
  - Functions: search, getArtists, getArtist, getAlbum, getSong, streamUrl, coverUrl, getPlaylists, getPlaylist, star, unstar, etc.

- [ ] 8. **Svelte stores**

  **Agent**: `unspecified-high`
  **Files**: `web/src/stores/player.js`, `web/src/stores/auth.js`, `web/src/stores/library.js`

  **What to do**:
  - player store: currentTrack, queue, isPlaying, progress, volume, shuffle, repeat
  - auth store: token, user, getToken/setToken/logout
  - library store: artists, albums, playlists

### Wave 3: Core UI

- [ ] 9. **Player bar + HTML5 audio**

  **Agent**: `visual-engineering` + `playwright`
  **Files**: `web/src/components/PlayerBar.svelte`, `web/src/lib/player.js`

  **What to do**:
  - Fixed bottom bar (80px, #181818 bg, #1DB954 accent)
  - Left: cover art 40x40, title, artist
  - Center: prev/play-pause/next + clickable progress bar
  - Right: volume slider, shuffle/repeat icons
  - Hidden `<audio>` element wired to player store
  - `streamUrl(id)` for audio src
  - `ended` event → next track
  - Keyboard shortcuts: Space, Ctrl+Arrow

- [ ] 10. **Search page**

  **Agent**: `visual-engineering`
  **Files**: `web/src/pages/Search.svelte`

  **What to do**:
  - Route: `/search`
  - Search input with 300ms debounce
  - Results: 3 sections (Artists grid, Albums grid, Songs list)
  - Click artist → /artist/:id, album → /album/:id, song → play
  - Empty state: "Search for artists, albums, or songs"

- [ ] 11. **Album + Artist pages**

  **Agent**: `visual-engineering`
  **Files**: `web/src/pages/Album.svelte`, `web/src/pages/Artist.svelte`, `web/src/components/TrackList.svelte`, `web/src/components/AlbumCard.svelte`

  **What to do**:
  - Album page: hero cover art, title, artist, year, Play All / Shuffle, tracklist
  - Artist page: name, album grid with cover art + year
  - TrackList: reusable sorted rows, play on click, highlight current
  - AlbumCard: cover thumbnail + label

- [ ] 12. **Library page**

  **Agent**: `visual-engineering`
  **Files**: `web/src/pages/Library.svelte`

  **What to do**:
  - Route: `/library`
  - Tabs: Artists | Albums | Playlists
  - Artists: A-Z sidebar index, card rows
  - Albums: grid of AlbumCards
  - Playlists: list with track counts

### Wave 4: Remaining Pages

- [ ] 13. **Playlist page + sidebar**

  **Agent**: `visual-engineering`
  **Files**: `web/src/pages/Playlist.svelte`, `web/src/components/Sidebar.svelte`

  **What to do**:
  - Playlist page: editable name, tracklist with drag-reorder, delete button
  - Sidebar: nav links (Search, Library), playlist list, New Playlist button
  - Add/remove tracks from context menu

- [ ] 14. **Auth callback + polish**

  **Agent**: `visual-engineering`
  **Files**: `web/src/pages/Callback.svelte`, `web/src/App.svelte`

  **What to do**:
  - Callback page: reads `#access_token`, stores it, redirects to /search
  - Loading/error/empty states for all pages
  - Page title updates with current track
  - Smooth transitions between pages

### Wave 5: Integration

- [ ] 15. **Build + embed test**

  **Agent**: `quick`
  **Files**: project root

  **What to do**:
  - `cd web && npm run build`
  - `cd .. && go build ./cmd/soultify/`
  - Run server, open browser, verify login → search → play flow
  - Fix any routing or embed issues

---

## Success Criteria

```bash
cd /home/tonio/Documentos/GitHub/soultify
go build ./... && cd web && npm run build && cd ..
./soultify serve
# Open http://localhost:4533/ → see Spotify-like UI
```

- Login flow: browser → `/auth/login` → Pocket-ID → callback → SPA
- Search finds "Could You Be Loved", clicking plays it
- Player bar shows progress, seeking works
- Album/artist/library pages render correctly
- Playlists CRUD works
- Page refresh preserves login
