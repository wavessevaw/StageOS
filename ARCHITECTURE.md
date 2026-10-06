# Release candidate 1.0.0-rc.1

Default startup creates an empty database in StageOS-Work; theatre initialization is a separate Setting. Demo routes are disabled by default and example modules are excluded from packaged runtime. Production template and validation are independent of seed data. Saved event cards use committed assignments/tasks/bookings; catalog edits do not silently rewrite them. See RELEASE_AUDIT_RU.md for remaining limits.

# Изменения 0.4

Каталог площадок создаёт отдельные механические ресурсы и сохраняет идентификаторы при редактировании. Имущество создаётся поштучно; production.items ссылается на конкретные ресурсы. rehearsal_people задаёт выборочный состав репетиции. notes хранит примечание. force требует причины и сохраняет все конфликты. Существующие JSON-запросы совместимы благодаря значениям по умолчанию.

## Изменения 0.3

backend/timing.py добавляет CP-SAT пересчёт цепочки по пользовательским временным закреплениям. Request хранит run_through и task_overrides; существующие события совместимы без миграции. backend/production_editor.py проверяет ссылки полного паспорта. Состав Preview содержит eligible_ids для ручных замен. Отклонение предложений изменяет только Audit. Статистика сотрудника вычисляется из Booking/Event.

# StageOS architecture

## Runtime

Shipped Portable: Win32 GUI launcher → bundled CPython → pywebview/WebView2 + loopback FastAPI → SQLAlchemy → SQLite.

An alternative Tauri host remains in src-tauri. Its build is blocked in this environment. The portable uses the same backend and React assets, but a different desktop host.
React assets are served by the same FastAPI instance; packaged Python includes static assets, migrations and OR-Tools native libraries. Windows WebView2 opens the loopback URL. The portable launcher owns a Python GUI process; that process runs the server on a thread and closes it when the window closes. The Tauri variant instead owns a backend child process. A random per-launch token protects `/api`; the UI transfers it from the initial URL into sessionStorage and removes it from browser history. Cross-origin API access is rejected. Local development can omit the token.

## Domain

`Resource` stores typed assets (person, venue, room, equipment, kit, vehicle, scenery, prop, costume, fly bar, soffit, lighting position). Common identifiers/statuses/departments are columns; technical attributes are JSON.

`Production` is permanent, versioned, and contains casts, eligible performers, responsible people, ensemble memberships, crew, inventories, requirements, venue adaptations and stage durations.

`Event` is a dated instance. Its snapshot stores original plan, request and assignments. `Booking` stores authoritative resource intervals. `Task` stores planned and actual stage intervals. `Audit` stores before/after and proposed plans. `Setting` stores optional AI configuration.

A normalized polymorphic resource table makes overlap checks uniform. Production JSON is a demo compromise: this simplifies deep catalogs, but database FKs do not validate every ID inside the production document. The engine validates IDs when constructing a plan. A production system should normalize memberships/roles and add typed schema validation for every passport edit.

## Deterministic planning

1. Validate command with Pydantic.
2. Resolve production, cast and venue; select explicit venue override when allowed.
3. Check geometry, fly system, working height, power, universes, gates, pit and scenery.
4. Model preparation with CP-SAT intervals, precedence, `NoOverlap`, `Cumulative`; maximize late starts subject to readiness before curtain.
5. Expand each kit into concrete equipment items. Allocate individual fly bars/soffits/lighting positions. Derive person call times and booking intervals.
6. Check resource states, availability intervals, other events and travel gaps. Explain each overlap with busy/required/overlap intervals.
7. Build Preview containing full plan, assignments, conflicts, solver status and a SHA-256 fingerprint.
8. On confirm, acquire write lock and SQLite `BEGIN IMMEDIATE`, repeat evaluation, reject changed fingerprint/version, enforce conflict policy, atomically persist event/tasks/bookings/audit.

The Preview endpoint never writes. Drag/drop and resize first revert the visible edit, then invoke the same Preview/confirmation flow. Explicit force permits saving CRITICAL incompatibilities with a mandatory reason while preserving conflicts and audit history. Invalid references and infeasible time anchors still fail. ERROR requires an administrative reason. Seed has an internal exceptional insert path to materialize intentionally conflicted demonstrations.

## Solver scope

Preparation uses real mandatory intervals, precedence, NoOverlap and cumulative crew capacity. Staffing substitutions use `OptionalIntervalVar`, `ExactlyOne`, per-person NoOverlap and penalties for changing the responsible person. Crew capacity is a demonstration assumption (10 simultaneous workers for 4/3/2/1 stage/light/sound/video demand), not a full skill-aware labor optimizer. Actual staff assignments are checked separately by Conflict Engine.

Rehearsal window discovery uses deterministic enumeration plus Core validation. Equipment replacements use bounded combinatorial evaluation. Venue checks are arithmetic and resource queries, not an LLM.

## Mutations and consistency

Event edits require version. Creation/editing fingerprints detect intervening conflicts. Cancelling frees all bookings. Proposal approval reevaluates and rejects stale plans. Maintenance/absence affects future previews and calendar status; existing snapshots remain available for audit. Resource status changes return affected event IDs.

SQLite is single-user/single-process. A process write mutex is sufficient with SQLite's immediate write lock for the supplied architecture. PostgreSQL migration requires transaction isolation/advisory or row locks across workers; changing the URL alone is not a production concurrency solution.

## Optional AI

An OpenAI-compatible chat completion endpoint receives a bounded question and current database snapshot. JSON commands must pass the same Request schema and Preview pipeline. There is no LLM database write tool. Disabled AI leaves the rest of the system unchanged. The connector currently omits token streaming, encrypted API-key storage, model installation and RAG indexing.

## Upstream references

- OR-Tools scheduling: https://developers.google.com/optimization/scheduling/job_shop
- Tauri external binaries: https://v2.tauri.app/develop/sidecar/
- Tauri configuration: https://v2.tauri.app/reference/config/
- FullCalendar React: https://fullcalendar.io/docs/react

Runtime dependency versions are recorded in npm locks and `requirements-lock.txt`. Rust dependencies are specified in Cargo.toml; Cargo.lock is absent because Cargo was unavailable.

## Database portability and conflict fixtures

SQLite imports validate the file signature, integrity, FK consistency, migration revision and ORM columns. They create a separate managed file and rebind future sessions. SQLite backup API exports a consistent copy. 24 diagnostic fixtures temporarily create actual bookings or alter typed requirements, run the same Preview engine, then roll back the transaction. They never return prewritten conflict results.

## Windows build evidence

The portable Win32 launcher is PE32+ x64 with Windows GUI subsystem, compiled using Zig 0.16.0. CPython and native dependencies are Windows distributions; checksums are in WINDOWS_RUNTIME_MANIFEST.json. Wine execution could not start because wineserver socket creation was denied by the execution environment. This is not a passed Windows smoke test.


## Local theatre accounts (1.0.3)

The production schema remains unchanged. A separate accounts.sqlite registry stores theatre IDs, database paths, salted password hashes, memberships and account audits. The HTTP workspace gateway authenticates requests and dispatches them to an application with its own SQLAlchemy Session for each theatre. No global session is rebound when switching theatres. Database import updates only that theatre’s persisted path. Runtime sessions are opaque, hashed in memory and do not survive server restart. Public builds contain no initial user credentials. The test-only core launcher flag is used explicitly by historical core UI regression suites; normal desktop and backend entrypoints always use the gateway.


## StageOS Server 1.0.4

The desktop localhost gateway owns connection.json and serves the bundled React UI. In host mode a second Uvicorn listener on 0.0.0.0 serves the same workspace registry/core apps. LAN requests require a random connection code followed by a per-user theatre session. Theatre creation and first-admin setup remain host-local. In client mode API requests are proxied to the selected host; binary exports and HttpOnly cookies are forwarded. No production data is copied to the client. HTTPX clients have no shared cookie jar across users.

SQLite databases and accounts.sqlite remain on the host. Thread locks serialize mutations across both event loops, while core fingerprints and event/production versions reject stale confirmations. Per-theatre revisions let React refresh every five seconds. Client connection failure returns 503 without a local-write fallback. Restart invalidates sessions. The host is not a Windows service. LAN transport is HTTP; internet access requires external HTTPS or VPN.

## Event planning 1.0.5

Request stores removed_tasks, extra_tasks and role_assignments in the event JSON. Production passports are unchanged. CP-SAT reconnects dependencies across removed stages, rejects cycles, pins custom stage times, and recalculates reservations. Main event cannot be removed. Preview fingerprint validation and transactional save protect the complete plan.

Confirmed history is grouped into relative-time templates per production/venue/event type (latest 200 eligible events). Two matching records are required. Forced, cancelled, draft and pending events are excluded. Candidates pass the deterministic preview engine again. Optional LLM only selects a validated candidate ID and explains it. No neural weight fine-tuning or automatic event writes occur. Ollama downloads the optional small model outside the application archive.


## Internet relay 1.0.9

`backend/tunnel.py` owns a separately downloaded ngrok 3.39.11 Windows x64 process. Download SHA-256 is pinned. The agent forwards only the existing LAN gateway, preserving connection code and theatre accounts. The public hello response carries a random per-server-start identity; a verified address also requires authenticated theatre-list access. Management is local-admin-only, and the LAN gateway rejects every `/api/connection` route. Host closes its agent before stopping the listener. Credentials are optional Windows DPAPI files and passed to the agent only via its environment. Config and logs contain no token; request inspection and remote management are disabled. Provider terminates public TLS, so this is not end-to-end encryption. No account-backed external smoke test has been performed.
