# Soultify — Phase 0: Foundation

## TL;DR

Build the core of a unified music streaming + Soulseek download Go binary with Subsonic API compatibility and OIDC auth. One binary replaces Navidrome (streaming) + slskd (download) + Lidarr (import) in a single coherent stack.

**Deliverables**: Go binary with music scanner, SQLite metadata, Subsonic streaming API, OIDC JWT auth, and a Helm chart to deploy it on the ton cluster alongside the existing stack.

**Estimated Effort**: 1-2 weeks
**Parallel Execution**: YES — 4 waves
**Critical Path**: Go module → SQLite schema → Scanner → Subsonic API → OIDC → Docker → Helm

---

## Context

### Original Request

User wants a single backend binary that integrates music streaming (Navidrome), Soulseek downloading (slskd), music management (Lidarr), requests (Aurral), and playlist creation (Explo) into one system with OIDC authentication via Pocket-ID.

### Existing Infrastructure
- **Cluster**: ton (home k8s cluster), Flux CD
- **Storage**: NFS-backed via 192.168.88.245 (large-storage StorageClass)
- **Auth**: Pocket-ID at `id.lag0.com.br`
- **Ingress**: Istio with wildcard cert `*.lag0.com.br`
- **Music path**: NFS at `192.168.88.245:/ton-cluster/navidrome_navidrome-music-pvc/`

### Key Design Decisions
- **Language**: Go (static binary, goroutines for concurrency, excellent subsonic/streaming support)
- **API Compatibility**: Subsonic API (v1.16) — so all existing mobile clients work immediately
- **Database**: SQLite (WAL mode, single-writer pattern)
- **Auth**: OIDC JWT Bearer token validation against Pocket-ID JWKS endpoint
- **No forking**: Build clean, import `go-soulseek` as external dependency

---

## Work Objectives

### Core Objective
Create a Go binary that scans a music directory, exposes a Subsonic-compatible streaming API with OIDC authentication, and provides the foundation for Soulseek download integration in Phase 1.

### Concrete Deliverables
- Go module `github.com/antoniolago/soultify`
- SQLite database with artists/albums/tracks schema
- Music scanner (walk directory, parse tags, populate DB)
- Inotify-based file watcher for automatic rescans
- Subsonic API subset (getArtists, getAlbum, getSong, stream, getCoverArt, search3, ping, getMusicFolders, getIndexes)
- OIDC JWT validation middleware (Pocket-ID)
- Cobra CLI (serve command, scan command)
- Multi-stage Dockerfile (~15MB binary)
- Helm chart (Deployment, PVC, Service, VirtualService, ConfigMap for OIDC settings)
- `.github/workflows/build.yaml` for CI

### Must Have
- Music scanner detects FLAC, MP3, OGG, WAV, ALAC, AAC files and extracts tags
- Subsonic API works with Symfonium/Ultrasonic/DSub mobile clients
- OIDC JWT validation protects all API endpoints
- Docker image builds reproducibly (multi-stage, distroless)
- Helm chart deploys to ton cluster with existing StorageClass

### Must NOT Have
- No transcoding (Phase 1)
- No Soulseek integration (Phase 1)
- No playlist management (Phase 2)
- No web UI (Phase 2)
- No request system (Phase 2)
- No ListenBrainz scrobbling (Phase 2)

---

## Verification Strategy

### QA Policy
- `go build ./...` must pass
- `go vet ./...` must pass
- Unit tests for scanner, Subsonic API, and auth middleware
- Manual verification: build Docker image, deploy via Helm, connect a mobile Subsonic app

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — 3 tasks):
├── T1: Go module + core types + config
├── T2: SQLite schema + DB layer
└── T3: CLI framework (cobra)

Wave 2 (Core — 3 tasks, ALL PARALLEL):
├── T4: Music scanner (taglib + file walker)
├── T5: File watcher (inotify)
└── T6: OIDC auth middleware (JWT validation)

Wave 3 (API — 2 tasks):
├── T7: Subsonic API implementation
└── T8: HTTP router + middleware wiring

Wave 4 (Deploy — 3 tasks, ALL PARALLEL):
├── T9: Multi-stage Dockerfile
├── T10: Helm chart
└── T11: CI workflow (GitHub Actions)
```

---

## TODOs

### Wave 1: Foundation

- [x] 1. **Go module + core types + config**

**Agent**: `deep`
**Skills**: none

**What to do**:
- Initialize Go module at `/home/tonio/Documentos/GitHub/soultify/`
- Create `pkg/types/types.go` with:
  ```go
  type Artist struct {
    ID            string // MusicBrainz ID or UUID
    Name          string
    AlbumCount    int
    CoverArtPath  string
    CreatedAt     time.Time
    UpdatedAt     time.Time
  }
  type Album struct {
    ID          string
    ArtistID    string
    Name        string
    Year        int
    Genre       string
    CoverArtPath string
    TrackCount  int
    Duration    float64
    CreatedAt   time.Time
  }
  type Track struct {
    ID         string
    AlbumID    string
    ArtistID   string
    Title      string
    TrackNumber int
    Duration   float64
    FilePath   string
    FileFormat string
    BitRate    int
    SampleRate int
    Size       int64
    Genre      string
    Year       int
    HasCoverArt bool
    CreatedAt  time.Time
  }
  ```
- Create `internal/config/config.go` with:
  ```go
  type Config struct {
    MusicFolder   string   // path to music library
    DBPath        string   // path to SQLite file
    ListenAddr    string   // :4533
    ScanInterval  string   // 12h
    OIDC struct {
      Enabled     bool
      Issuer      string // https://id.lag0.com.br
      ClientID    string
      JWKSEndpoint string // .well-known/openid-configuration discovery
      Audience    string
    }
    LogLevel      string
  }
  ```
  Support config via YAML file + env vars + CLI flags (Viper).
- Create `internal/app/app.go` with the application struct that holds config, DB, scanner, etc.

**Must NOT do**:
- Don't add any business logic yet
- Keep types minimal (extend in later phases)

**Parallelization**:
- Wave: 1
- Blocks: T2, T3
- Blocked By: None

**Acceptance Criteria**:
- [ ] `go build ./...` compiles
- [ ] `soultify --help` shows serve and scan commands
- [ ] Config loads from env vars
- [ ] Types compile and are serializable to JSON

- [x] 2. **SQLite schema + DB layer**

**Agent**: `deep`
**Skills**: none

**What to do**:
- Create `internal/db/schema.go` with:
  ```sql
  CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    album_count INTEGER DEFAULT 0,
    cover_art_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS albums (
    id TEXT PRIMARY KEY,
    artist_id TEXT NOT NULL REFERENCES artists(id),
    name TEXT NOT NULL,
    year INTEGER,
    genre TEXT,
    cover_art_path TEXT,
    track_count INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
  CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    album_id TEXT NOT NULL REFERENCES albums(id),
    artist_id TEXT NOT NULL REFERENCES artists(id),
    title TEXT NOT NULL,
    track_number INTEGER,
    duration REAL DEFAULT 0,
    file_path TEXT NOT NULL UNIQUE,
    file_format TEXT,
    bit_rate INTEGER,
    sample_rate INTEGER,
    size INTEGER,
    genre TEXT,
    year INTEGER,
    has_cover_art INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX idx_albums_artist ON albums(artist_id);
  CREATE INDEX idx_tracks_album ON tracks(album_id);
  CREATE INDEX idx_tracks_artist ON tracks(artist_id);
  ```
- Create `internal/db/db.go` with:
  - `Open(path string) (*sql.DB, error)` — opens and configures WAL mode
  - `RunMigrations(db *sql.DB) error` — creates tables
  - Repository functions:
    - `UpsertArtist`, `UpsertAlbum`, `UpsertTrack`
    - `GetArtist(id)`, `GetAlbum(id)`, `GetTrack(id)`
    - `GetArtists()`, `GetAlbums(artistID)`, `GetTracks(albumID)`
    - `DeleteArtist(id)`, `DeleteAlbum(id)`, `DeleteTrack(id)`
    - `SearchArtists(query)`, `SearchAlbums(query)`, `SearchTracks(query)`
    - `GetStats()` — artist/album/track counts, total duration
- Use `database/sql` with `mattn/go-sqlite3` driver
- Enable WAL mode: `PRAGMA journal_mode=WAL`
- Enable foreign keys: `PRAGMA foreign_keys=ON`
- Use a single write goroutine channel pattern to avoid `database is locked` errors

**Must NOT do**:
- Don't use an ORM — raw SQL is simpler and more transparent
- Don't add migration framework — just CREATE IF NOT EXISTS for now

**Parallelization**:
- Wave: 1
- Blocks: T4, T7
- Blocked By: T1

**Acceptance Criteria**:
- [ ] Migrations create all tables with correct schema
- [ ] CRUD operations work
- [ ] Search returns results quickly (< 100ms for 50k tracks)
- [ ] SQLite WAL mode is enabled

- [x] 3. **CLI framework (cobra)**

**Agent**: `quick`
**Skills**: none

**What to do**:
- Create `cmd/soultify/main.go` using Cobra
- Commands:
  - `serve` — starts the HTTP server with Subsonic API
  - `scan` — one-shot scan of music directory, then exit
  - `version` — prints version
- Global flags:
  - `--config` / `SOULTIFY_CONFIG` path to config file
  - `--music-folder` / `SOULTIFY_MUSIC_FOLDER`
  - `--db-path` / `SOULTIFY_DB_PATH`
  - `--listen` / `SOULTIFY_LISTEN_ADDR`
  - `--log-level` / `SOULTIFY_LOG_LEVEL`
- `serve` subcommand flags:
  - `--oidc-enabled` / `SOULTIFY_OIDC_ENABLED`
  - `--oidc-issuer` / `SOULTIFY_OIDC_ISSUER`
  - `--oidc-client-id` / `SOULTIFY_OIDC_CLIENT_ID`
  - `--oidc-audience` / `SOULTIFY_OIDC_AUDIENCE`
- Initialize config via Viper (yaml file → env → flags)
- Initialize logger (zerolog, output to stderr)

**Must NOT do**:
- Don't implement server logic here — just wire CLI to app

**Parallelization**:
- Wave: 1
- Blocks: T8
- Blocked By: T1

**Acceptance Criteria**:
- [ ] `go run ./cmd/soultify serve --help` shows all flags
- [ ] Config loads from env vars with SOULTIFY_ prefix
- [ ] Config loads from YAML file
- [ ] CLI flags override env vars

### Wave 2: Core

- [x] 4. **Music scanner (taglib + file walker)**

**Agent**: `deep`
**Skills**: none

**What to do**:
- Create `internal/media/scanner.go`:
  - `Scan(musicFolder string, db *sql.DB, progressFn func(string)) error`
  - Walk all files recursively
  - Skip non-audio files (check extension: .flac, .mp3, .ogg, .wav, .m4a, .aac, .alac, .wma, .dsf, .ape)
  - Parse tags using a taglib library:
    - For Go, use `github.com/dhowden/tag` (pure Go tag reader, supports FLAC, MP3, OGG, M4A)
    - Extract: title, artist, album, albumartist, track number, genre, year, duration, cover art
  - Detect if file has embedded cover art (for getCoverArt endpoint)
  - Use MusicBrainz Picard-style file/folder structure if available:
    - `Artist/Album/TrackNumber - Title.ext`
  - For each file, upsert artist → album → track in DB
  - For removed files (detected by comparing DB paths with filesystem): delete from DB
  - Report progress: `"Scanning: Artist - Album (45/320 files)"`
  - Track elapsed time
  - Log summary at end: "Scanned 12,450 files, found 342 artists, 1,245 albums, 12,450 tracks in 2m34s"

**Must NOT do**:
- Don't parse cover art data into DB — just mark `has_cover_art` (cover art is served from filesystem on demand)
- Don't handle transcoding

**Parallelization**:
- Wave: 2
- Blocks: T7 (needs populated DB)
- Blocked By: T2

**Acceptance Criteria**:
- [ ] Scanner processes 50 test files correctly
- [ ] Artist/album/track counts match filesystem
- [ ] Tags are extracted: title, artist, album, year, genre
- [ ] Rescan is incremental (only processes changed files)
- [ ] Deleted albums are removed from DB

- [x] 5. **File watcher (inotify)**

**Agent**: `unspecified-high`
**Skills**: none

**What to do**:
- Create `internal/media/watcher.go`:
  - `Watch(musicFolder string, onChange func()) error`
  - Use `github.com/fsnotify/fsnotify` (Go inotify library)
  - Watch for: Create, Write, Remove, Rename events
  - Debounce events: batch changes within a 30-second window, then trigger a scan
  - Handle symlinks (common in Lidarr-managed libraries)
  - Handle k8s volume mounts (NFS might not support inotify — detect and fall back to periodic scanning)
  - If inotify is unavailable (NFS): log warning and fall back to scan interval from config
- Integrate with scanner (T4): when watcher triggers, call `Scan()`

**Must NOT do**:
- Don't implement complex coalescing of events — simple debounce is sufficient

**Parallelization**:
- Wave: 2
- Blocks: None (runs as goroutine alongside serve command)
- Blocked By: T4

**Acceptance Criteria**:
- [ ] Watcher detects file changes on local filesystems
- [ ] Watcher falls back gracefully on NFS mounts
- [ ] Debounce works: 5 rapid changes trigger 1 scan, not 5

- [x] 6. **OIDC auth middleware (JWT validation)**

**Agent**: `deep`
**Skills**: none

**What to do**:
- Create `internal/auth/oidc.go`:
  - `NewMiddleware(issuer, audience string) (func(http.Handler) http.Handler, error)`
  - On startup: fetch JWKS from `{issuer}/.well-known/openid-configuration`, then get JWKS URL from the response, then fetch public keys
  - Cache JWKS keys with periodic refresh (every hour)
  - Extract JWT from:
    - `Authorization: Bearer <token>` header
    - `access_token` cookie (for web UI)
  - Validate: signature (RS256/ES256), expiry (`exp`), issuer (`iss`), audience (`aud`)
  - On success: inject claims into request context (`context.WithValue`)
  - On failure: return 401 with Subsonic-compatible error XML
  - Public endpoints (no auth required):
    - `/rest/ping` — Subsonic requires this unauthenticated
    - `/health` — k8s liveness probe
    - `/rest/getMusicFolders` — some clients need this before auth
  - Use `github.com/golang-jwt/jwt/v5` for JWT parsing
  - Use `github.com/MicahParks/keyfunc` for JWKS key rotation
  - Log authentication failures (warn level, without the token)

**Must NOT do**:
- Don't implement user management — Pocket-ID handles that
- Don't implement sessions — purely JWT-based

**Parallelization**:
- Wave: 2
- Blocks: T8 (router needs auth middleware)
- Blocked By: T1

**Acceptance Criteria**:
- [ ] Valid Pocket-ID JWT passes middleware
- [ ] Expired JWT returns 401
- [ ] Missing JWT returns 401
- [ ] JWKS keys are cached and refreshed
- [ ] Public endpoints bypass auth

### Wave 3: API

- [x] 7. **Subsonic API implementation**

**Agent**: `deep`
**Skills**: none

**What to do**:
- Create `pkg/subsonic/handler.go`, `pkg/subsonic/responses.go`, `pkg/subsonic/params.go`
- Implement Subsonic API v1.16.1 with OpenSubsonic extensions
- Response format: XML by default (`f=json` for JSON)
- Endpoints to implement:

  **Required for mobile client compatibility:**
  - `GET /rest/ping` → returns `<subsonic-response status="ok">`
  - `GET /rest/getMusicFolders` → return default folder (id=1, name="Music")
  - `GET /rest/getIndexes` → return alphabet-based artist index
  - `GET /rest/getArtists` → return all artists with indexes
  - `GET /rest/getArtist` → artist details + album list
  - `GET /rest/getAlbum` → album details + track list
  - `GET /rest/getSong` → single track metadata
  - `GET /rest/stream` → stream audio file (support Range header for seeking)
  - `GET /rest/getCoverArt` → return embedded cover art or folder.jpg
  - `GET /rest/search3` → search across artists/albums/tracks

  **Optional but nice:**
  - `GET /rest/getPlaylists` → empty list for now
  - `GET /rest/getNowPlaying` → empty for now
  - `GET /rest/getAlbumList2` → random/recent/frequent/alphabetical
  - `GET /rest/getRandomSongs` → random tracks
  - `GET /rest/getGenres` → genre list
  - `GET /rest/scrobble` → accept but no-op (Phase 2 adds ListenBrainz)

- **Stream endpoint (`/rest/stream`)**: 
  - Support `Range` header for seeking
  - Support `maxBitRate` parameter for transcoding (Phase 1 feature, for now just serve raw)
  - Support `format` parameter (if absent, serve raw)
  - Set correct Content-Type based on file extension
  - Set Accept-Ranges: bytes
  - Use `http.ServeContent` for efficient Range handling

- **Cover art endpoint (`/rest/getCoverArt`)**:
  - Check for embedded cover art in the file
  - Fall back to `cover.jpg`, `folder.jpg`, `AlbumArt*.jpg` in album directory
  - Cache cover art in a separate directory (`/data/covers/`)
  - Resize to reasonable size (300x300 WebP recommended)

- **Search endpoint (`/rest/search3`)**:
  - Query parameter `query` — search term
  - Return matching artists, albums, tracks
  - Support `artistCount`, `albumCount`, `songCount` limits
  - Full-text search via SQLite LIKE (upgrade to FTS5 in Phase 2 if needed)

- Error handling: return proper Subsonic error codes:
  - 0: Generic error
  - 10: Missing parameter
  - 20: Authentication required (if OIDC is disabled but user/pass is missing)
  - 30: Authentication failed
  - 40: Wrong username/password

**Must NOT do**:
- Don't implement transcoding (Phase 1)
- Don't implement chat/radio/podcast endpoints (Phase 2+)

**Parallelization**:
- Wave: 3
- Blocks: None (API layer)
- Blocked By: T4 (needs scanner to populate DB), T2 (needs DB queries)

**Acceptance Criteria**:
- [ ] Symfonium/Ultrasonic mobile app connects and browses library
- [ ] Stream plays audio with seeking (Range header)
- [ ] Cover art displays in client
- [ ] Search returns results
- [ ] Invalid tokens return proper error codes

- [x] 8. **HTTP router + middleware wiring**

**Agent**: `unspecified-high`
**Skills**: none

**What to do**:
- Create `internal/api/router.go`:
  - Set up `gorilla/mux` router
  - Mount Subsonic API at `/rest/`
  - Add health endpoint at `/health`
  - Wire middleware stack:
    1. Recovery middleware (catch panics, return 500)
    2. Logger middleware (zerolog, log method/path/status/duration)
    3. Request ID middleware
    4. Auth middleware (T6) on Subsonic routes (except `/rest/ping`)
  - Handle CORS headers (for web UI development)
  - Handle Content-Type negotiation (JSON vs XML based on `f` parameter)
  - Add rate limiting via `golang.org/x/time/rate` (optional, can be omitted for now)

**Must NOT do**:
- Don't add request validation — let Subsonic handler handle it

**Parallelization**:
- Wave: 3
- Blocks: T9, T10, T11 (wiring needed for deploy)
- Blocked By: T6, T7, T3

**Acceptance Criteria**:
- [ ] `/rest/ping` returns 200 without auth
- [ ] `/rest/getArtists` returns 401 without JWT
- [ ] `/rest/getArtists` returns 200 with valid JWT
- [ ] `/health` returns 200
- [ ] All requests are logged

### Wave 4: Deploy

- [x] 9. **Multi-stage Dockerfile**

**Agent**: `unspecified-high`
**Skills**: none

**What to do**:
- Create `Dockerfile`:
  ```dockerfile
  # Stage 1: Build
  FROM golang:1.22-alpine AS builder
  RUN apk add --no-cache gcc musl-dev
  WORKDIR /src
  COPY go.mod go.sum ./
  RUN go mod download
  COPY . .
  RUN CGO_ENABLED=1 go build -ldflags="-s -w" -o /soultify ./cmd/soultify

  # Stage 2: Runtime
  FROM gcr.io/distroless/base-debian12:nonroot
  COPY --from=builder /soultify /
  EXPOSE 4533
  ENTRYPOINT ["/soultify", "serve"]
  ```
- Create `.dockerignore` (exclude .git, .github, test files)
- Verify: `docker build -t soultify:latest .` produces ~15MB image

**Must NOT do**:
- Don't use alpine for runtime (distroless is smaller and more secure)

**Parallelization**:
- Wave: 4
- Blocks: T10 (Helm needs image)
- Blocked By: T8

**Acceptance Criteria**:
- [ ] Image builds successfully
- [ ] Image size < 20MB
- [ ] Container starts and serves `/health`
- [ ] Container runs as non-root user

- [x] 10. **Helm chart**

**Agent**: `unspecified-high`
**Skills**: none

**What to do**:
- Create `deploy/helm/soultify/`:
  - `Chart.yaml` — name: soultify, version: 0.1.0
  - `values.yaml`:
    ```yaml
    replicaCount: 1
    image:
      repository: ghcr.io/antoniolago/soultify
      tag: latest
      pullPolicy: IfNotPresent
    config:
      musicFolder: /music
      dbPath: /data/soultify.db
      listenAddr: ":4533"
      logLevel: info
      oidc:
        enabled: true
        issuer: https://id.lag0.com.br
        clientID: soultify
        audience: soultify
    persistence:
      music:
        enabled: true
        existingClaim: "navidrome-music-pvc"
        # OR create new claim:
        # storageClass: large-storage
        # size: 100Gi
      data:
        enabled: true
        size: 10Gi
        storageClass: large-storage
    service:
      type: ClusterIP
      port: 4533
    virtualService:
      enabled: true
      host: music.lag0.com.br
      gateway: istio-system/lag0-gateway
    ```
  - `templates/deployment.yaml`
  - `templates/service.yaml`
  - `templates/pvc.yaml` (data PVC only)
  - `templates/virtualservice.yaml`
  - `templates/configmap.yaml` (for OIDC settings)
- Follow existing patterns from lag0-fleet-manifests (kavita-ton, lidarr-ton)
- ConfigMap holds non-sensitive config; secrets (OIDC client secret) come from Vaultwarden
- Mount music path as read-only, data path as read-write

**Must NOT do**:
- Don't add init containers yet
- Don't add HPA or PDB (Phase 2+)

**Parallelization**:
- Wave: 4
- Blocks: None
- Blocked By: T9

**Acceptance Criteria**:
- [ ] `helm template` produces valid k8s manifests
- [ ] Deployment has correct volume mounts
- [ ] VirtualService matches the repo convention (istio-system/lag0-gateway)
- [ ] Pod mounts /music (read-only) and /data (read-write)

- [x] 11. **CI workflow (GitHub Actions) — commented out, uses Forgejo**

**Agent**: `quick`
**Skills**: none

**What to do**:
- Create `.github/workflows/build.yaml`:
  ```yaml
  name: Build
  on: [push, pull_request]
  jobs:
    build:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-go@v5
          with:
            go-version: '1.22'
        - run: go build ./...
        - run: go vet ./...
        - run: go test ./...
  ```

**Must NOT do**:
- Don't add Docker push unless the user requests it

**Parallelization**:
- Wave: 4
- Blocks: None
- Blocked By: T1

**Acceptance Criteria**:
- [ ] CI passes on push

---

## Wave Dependencies

```
Wave 1: T1 → T2, T3
Wave 2: T2 → T4; T4 → T5; T1 → T6
Wave 3: T4 + T2 → T7; T3 + T6 + T7 → T8
Wave 4: T8 → T9; T9 → T10; T1 → T11
```

## File Structure (final)

```
/home/tonio/Documentos/GitHub/soultify/
├── .github/workflows/build.yaml
├── cmd/soultify/main.go
├── internal/
│   ├── api/router.go
│   ├── app/app.go
│   ├── auth/oidc.go
│   ├── config/config.go
│   ├── db/
│   │   ├── db.go
│   │   └── schema.go
│   └── media/
│       ├── scanner.go
│       └── watcher.go
├── pkg/
│   ├── subsonic/
│   │   ├── handler.go
│   │   ├── responses.go
│   │   └── params.go
│   └── types/types.go
├── deploy/helm/soultify/
│   ├── Chart.yaml
│   ├── values.yaml
│   └── templates/
│       ├── deployment.yaml
│       ├── service.yaml
│       ├── pvc.yaml
│       └── virtualservice.yaml
├── Dockerfile
├── .dockerignore
├── go.mod
└── go.sum
```

---

## Success Criteria

### Verification Commands
```bash
go build ./...
go vet ./...
docker build -t soultify:latest .
helm template deploy/helm/soultify --values deploy/helm/soultify/values.yaml | kubectl apply -f- --dry-run=client
```

### Final Checklist
- [ ] Binary compiles and CLI commands work
- [ ] SQLite schema created and queryable
- [ ] Scanner populates DB from FLAC/MP3 files
- [ ] Subsonic `ping` returns OK
- [ ] Subsonic `getArtists` returns artist list
- [ ] Subsonic `stream` serves audio with seeking
- [ ] Subsonic `getCoverArt` returns album art
- [ ] OIDC middleware rejects unauthenticated requests
- [ ] OIDC middleware accepts valid Pocket-ID JWT
- [ ] Docker image builds < 20MB
- [ ] Helm chart generates valid k8s manifests
- [ ] Mobile client (Symfonium/Ultrasonic) connects and plays music
