# Soultify — Phase 1: Soulseek On-Demand Streaming

## Goal
Search the Soulseek P2P network from the soultify search page, download on-demand, auto-import, and play. This replaces the need for Lidarr + slskd for music discovery.

---

## What needs to happen

When user searches for a song not in local library → query Soulseek network → return results in search page → user clicks play → download starts → file streams as it downloads → auto-imports to library when complete.

---

## Implementation Plan

### 1. Add go-soulseek dependency

Import `github.com/dlanileonardo/go-soulseek` (or the user's fork at `github.com/lag0/go-soulseek`) into go.mod. This library handles the Soulseek TCP protocol: login, search, browse, download.

### 2. Create `internal/soulseek/client.go`
- `type Client struct` — wraps go-soulseek with reconnect logic, handles login with username/password
- `func New(username, password string) *Client`
- `func (c *Client) Search(query string) ([]SearchResult, error)` — returns results with filename, peer username, bitrate, size, file extension
- `func (c *Client) Download(result SearchResult, destDir string) (filePath string, err error)` — downloads a file from a peer, saves to destination
- `func (c *Client) Connect() error` / `Disconnect()`
- Config: Soulseek username/password from env vars

### 3. Add Soulseek config to `internal/config/config.go`
```go
Soulseek struct {
    Username string `yaml:"username"`
    Password string `yaml:"password"`
}
```

### 4. Extend search API (`pkg/subsonic/handler.go`)
When `search3` is called with a query that returns few/no local results, also query Soulseek via the client. Return combined results. Add a flag to indicate external results.

### 5. Add download/subsonic endpoint
- `POST /rest/soulseekDownload` — triggers a Soulseek download for a given search result ID
- Returns download status immediately
- Download runs in background goroutine
- Progress tracked in DB

### 6. Auto-import completed downloads
- When download completes, file moves to music library folder
- Scanner re-scans the new file → it appears in library
- DB tracks download status (pending/downloading/complete/error)

### 7. Frontend changes
- Search results show Soulseek results with a "Download" or "Stream" button
- Download progress indicator in the UI
- When download completes, track appears in library automatically
- Player can play partially downloaded files (if format supports it)

---

## Files to create/modify

| File | Action |
|---|---|
| `internal/soulseek/client.go` | Create — Soulseek client wrapper |
| `internal/soulseek/types.go` | Create — Soulseek search result types |
| `internal/config/config.go` | Modify — add Soulseek config |
| `internal/app/app.go` | Modify — wire Soulseek client |
| `pkg/subsonic/handler.go` | Modify — add soulseekSearch + soulseekDownload handlers |
| `pkg/subsonic/responses.go` | Modify — add external result types |
| `pkg/subsonic/params.go` | No change |
| `internal/db/schema.go` | Modify — add downloads table |
| `internal/db/downloads.go` | Create — download tracking |
| `web/src/lib/subsonic.js` | Modify — add soulseek search/download API |
| `web/src/pages/Search.svelte` | Modify — show Soulseek results with Download button |

---

## Order of work

1. `go-soulseek` dependency + basic client wrapper (connect, search, download)
2. Soulseek config + wiring into app
3. Search endpoint that queries Soulseek
4. Download endpoint (background + progress tracking)
5. Auto-import into music library
6. Frontend search results + download buttons
7. Integration testing

---

Ready to start? This is ~1 week of work. First step: add the go-soulseek library and get a basic search working.
