# Gemini Accounts 1.5.3 — provider cleanup, API key rotation and agent reliability

- Removes Grok, Kimi and OpenCode from the application UI, team inventory and newly published client model routes. Existing credential/config backups remain available for rollback.
- Keeps API key rotation limited to compatible profiles (same endpoint, protocol and exact model), records exhausted/unavailable states, and reports when no usable tokens or quota remain.
- Stops retry storms for deterministic `auth_unavailable` agent failures and keeps transient provider retries cancellable.
- Restricts agent teams to Google, ChatGPT and Claude accounts while retaining one-account request serialization and peer-review safeguards.
- Distinguishes request/concurrency throttling from exhausted credits, respects per-key/model cooldowns across restarts, and automatically rechecks on a later request. Editing a credential invalidates its old cooldown.
- Gives agents a final tool-free turn at the step limit, includes explicit role permissions in planning, and uses another independent reviewer if one fails.

# Gemini Accounts 1.5.2 — Anthropic history and team route recovery

- Removes only malformed trailing `thinking` blocks from replayed Anthropic assistant history; normal thinking, text, tool calls and user content remain intact.
- Recovers temporary `ga-team-*` account routes after an interrupted run, reuses a durable lease when safe, and cleans orphaned prefixes before the next team.

# Gemini Accounts 1.5.1 — Account cooldowns and actionable team failures

- Waits for the selected account/model's native cooldown and Retry-After before retrying a temporary provider failure. Repeated requests no longer consume all retries during the gateway's one-minute recovery pause. Waiting remains cancellable and bounded by the saved run-time limit.
- Shows agents waiting for a retry in the task board and chat progress. Final provider failures include feedback for the affected agent, including the coordinator, so partial results retain the actual access/quota error.
- Keeps provider HTTP statuses for non-streaming team failures and includes status metadata in streamed error events. A fresh delivery after a finished failed run can retry instead of returning the cached failure.
- Retains the user's saved roster and account pins. Provider subscription, balance and access restrictions still require an available account; the program does not silently switch to another credential.

# Gemini Accounts 1.5.0 — Teams inside Claude and Flua connections

- Adds an Agent team model and a local MCP bridge for delegating from an existing Claude Desktop or Claude Code conversation to the roster saved in the manager. Connecting preserves existing client models, environment settings and other MCP servers; restart the client when convenient to load its new configuration.
- Passes the current model request's conversation history to the team as a paginated reference. MCP callers can supply relevant context explicitly. Other chats and project conversations are not read automatically.
- Shows chat-launched runs in the manager with a shared task board, stop controls and encrypted history. One team runs at a time; duplicate delivery of the same chat request reuses its run.
- Adds paginated text/code/DOCX/PDF reading and project text search. Long agent conversations are compacted within the request budget while preserving their full encrypted history. PDF image scans still require OCR.
- Allows the coordinator to use explicitly enabled project commands during analysis and validation. Reviewed file writes retain their separate permission and final-stage checks.
- Adds a Flua preset with its API host and Opus 5.5 ID. API checks, model discovery and provider forwarding identify Gemini Accounts instead of using Python's default User-Agent, which some API frontends reject with HTTP 403. Normalizes forwarded header casing to prevent duplicate JSON media types and resulting HTTP 400 errors. Changing an API server requires entering its key again.

# Gemini Accounts 1.4.1 — Usable team controls

- Allows preparing and saving a team while team mode is off. The opt-in checkbox sits beside the task actions, with an explanation of what is needed before starting.
- Shows validation, refresh and export feedback inside the team panel. Unavailable start, stop, export and remove actions explain their requirements.
- Keeps participant IDs unique when adding after a deletion, and prevents repeated stop requests while cancellation is in progress.
- Primes full Google weekly quota buckets in the background immediately after fresh startup quota loading. Each bounded greeting is pinned to its account and quota family, uses a registered low-effort metered model, and retains persistent cooldowns across restarts. Paused, restricted, reserved or exhausted accounts are skipped. Post-request quota observations distinguish an HTTP response from confirmed weekly consumption.

# Gemini Accounts 1.4.0 — Configurable agent teams, OpenCode and Kimi

- Adds an opt-in Team tab with 1–100 configurable participants, per-agent account/model/role/instructions, separate histories, a shared task board, messages, peer review, revisions and final synthesis. Mixed Google and ChatGPT teams can use available models including GPT-6 Luna.
- Separates team size from concurrent request limits. Requests are pinned to their selected account using reversible native model prefixes; agents sharing an account serialize requests and share its quota.
- Adds bounded provider requests, time, tool steps and output length; stop controls; encrypted run history and Markdown export. The feature remains disabled until the user enables it and starts a task.
- Supports research/web tasks and project files. Workers and reviewers prepare results without writing project files; the coordinator may apply reviewed changes only when the user enables writes. File writes check the current content hash and retain encrypted backups. Optional commands run with the current user's permissions.
- Connects OpenCode through a separately named provider while preserving other providers, agents and model choices. Existing JSON/JSONC config is backed up reversibly.
- Adds Kimi Code account sign-in for kimi.com/kimi.ai, account/model display and separate client routes. Model availability still depends on the account's actual plan.

# Gemini Accounts 1.3.14 — Grok visibility in Claude Desktop

- Publishes Grok models using stable client-compatible route names while retaining their Grok labels. Claude Desktop no longer drops raw `grok-*` entries during model validation.
- Pins these routes to the native xAI channel, preserves conversation history and tools, and scopes cooldowns to Grok accounts. Existing custom routes and client settings remain intact.
- Migrates previously connected Desktop presets automatically. Existing raw Grok routes remain available for older clients and conversations.

# Gemini Accounts 1.3.13 — Compact Claude model pickers

- Shows each Google-backed Claude Opus/Sonnet model once and retains only Gemini 3.8 Flash High, Medium and Low in the Claude Desktop picker. Older Flash, Pro, Lite, Google Haiku and duplicate selected-model entries are omitted from the picker.
- Uses Claude Code's supported `modelPicker` setting for the same explicit lineup (Claude Code 2.1.242 or newer). GPT, configured API-key and connected subscription/provider models retain their separate routes.
- Keeps hidden legacy routes usable by existing conversations and background search calls. No accounts, credentials or provider models are removed by the presentation filter.
- New installations use Flash 3.8 High/Low for the legacy Gemini defaults. Existing model preferences and client host rules are retained.

# Gemini Accounts 1.3.12 — Grok, token capacity and account diagnostics

- Adds a Grok/xAI account panel with gateway OAuth, account status and model discovery. Quota bars remain absent when the gateway/provider reports no quota windows.
- Adds empirical token-capacity estimates by provider, plan, model and quota window. Estimates require three clean samples, show the observed range, and exclude resets, missing data and mixed-model intervals.
- Adds OAuth credential uptime to account cards. Only explicit account-blocked or reauthentication-required states stop the timer; rate limits, temporary errors and manual pauses do not.
- Adds Google sign-in support for a separate browser profile by copying the authorization link and, when necessary, pasting the complete local callback URL. The callback is validated against the active redirect and state, forwarded only to the loopback gateway, and not persisted by the application.
- Adds configurable Windows tray notifications for reauthentication and quota-reserve transitions. Repeated polling does not repeat an alert; transient 429/network errors are not notified.
- Adds per-account time-to-reserve estimates from recent quota-drop intervals, compared with the provider reset time. The display stays empty until enough clean samples exist and labels the forecast as approximate.
- Scopes Grok quota waits to the xAI pool, independently of Google and ChatGPT restrictions. Conversation history and ordinary tool calls retain their original route.
- Keeps the manual Google callback action available after a rejected callback and ignores late replies from cancelled login sessions.
- Rebases quota measurements after the first historical usage snapshot, so previous-session tokens do not distort a new estimate. Invalid and future measurement timestamps are excluded from ETA.

# Gemini Accounts 1.3.11 — Websites and search in Claude Desktop

- Allows website access in the managed Claude Desktop profile. Existing installations with no host policy are migrated; explicit user host rules and other profile settings are retained during setup and model updates.
- Routes Claude Desktop's separate WebSearch requests to an available search-capable Gemini or ChatGPT model when the selected Google Claude/API model cannot run native search. The main conversation, its selected model, history and ordinary tool calls remain on their original route.
- Retains native search for supported Google, ChatGPT and Claude subscription routes. Reports an actionable error if no search-capable account is connected.
- Validates that the provider actually returned search results. Plain text and remembered links are not accepted as a completed search; another available search model is tried before any answer reaches Desktop.
- Existing Desktop conversations retain their network snapshot. Start a new conversation after applying the corrected profile.

# Gemini Accounts 1.3.10 — Account priorities and quota reserves

- Adds per-account priorities (0–999). Available accounts with larger priorities go first; equal priorities retain automatic quota/reset ordering. Exhaustion and provider restrictions remain effective.
- Adds draggable reserve markers and exact percentage entry on Google, ChatGPT and Claude subscription quota tracks. The default 0% retains previous behavior. Reserves apply independently to provider families/windows and future requests; unknown measurements are held until refreshed.
- Uses reserve-owned native model exclusions and restores only those rules after recovery or clearing a reserve. Existing user exclusions remain intact. Settings restoration clears reserve-owned rules before dropping preferences.
- Adds collapsible Google/subscription account lists and pooled quota summaries with compact indicators. Missing quota stays distinct from zero. Hidden lists leave the sidebar footer anchored to the bottom.
- Adds service visibility, language and theme settings accessible from compact mode. Hiding a service retains account sign-ins, routing and background quota monitoring.
- Reuses subscription cards and reordered Google cards, and avoids unchanged quota row redraws. The PySide6 interface is retained; functionality is adapted from Omni 1.4.6.

# Gemini Accounts 1.3.9 — Claude subscription accounts

- Adds a separate Claude account tab with normal Firefox sign-in, selected OAuth JSON import, quota display, pause/remove and a pinned response test.
- Publishes distinct Claude subscription model routes in the native Claude channel. They do not fall through to Google accounts or API-key profiles with the same model name.
- Ranks the Claude pool independently, caches usage reads for five minutes and distinguishes Opus/Sonnet weekly limits from account-wide exhaustion.
- Preserves conversation payloads and native account failover. Existing sign-ins are not imported automatically, paid extra usage is not enabled, and no synthetic assistant responses are generated.
- Includes Russian and English Windows guides in the installer. ChatGPT and Claude authentication/generation on real accounts still need user verification; automated tests use synthetic credentials and local servers.

# Gemini Accounts 1.3.8 — Firefox authorization

- ChatGPT sign-in opens a normal Firefox tab in the existing profile, as requested. It no longer launches a private Edge window or creates a temporary browser profile.
- Finds Firefox through its Windows App Paths registration, standard installation folders or PATH. Missing Firefox produces an error without silently selecting another browser.
- Preserves the existing OAuth flow, account storage and client model routes.

# Gemini Accounts 1.3.7 — ChatGPT accounts and compatible API model routes

- Fixes API models missing from Claude Desktop: opaque local IDs pass its model filter while display labels, provider credentials and upstream model IDs remain accurate. Legacy API routes keep working.
- Adds a ChatGPT tab with isolated browser sign-in, selected auth.json import, per-account plan/quota display, independent reset-priority routing, pause/remove and a short response test.
- Shows available ChatGPT usage-reset credits and requires confirmation before consuming one. Existing Codex sign-ins are never imported automatically; background generation probes are off by default.
- Tries another compatible API key on provider rejection or connection failure, before any response content. Keys must share the exact upstream model, provider URL and protocol; pause and per-key opt-out are respected. Each actual attempt has separate statistics.
- Rechecks provider cooldowns on each poll after HTTP 429 so a newly available account wakes a waiting request. Google, ChatGPT and API waits remain separate.
- Adds account-name privacy, subscription plan labels, independent Gemini/Claude quota status and card updates without periodic rebuilding.
- Adapts reviewed MIT upstream functionality through cfec649 while retaining the PySide6 interface and five languages. Full request-text logging is not enabled or included.

# Gemini Accounts 1.3.6 — Quota availability and client model menus

- Corrects pooled quota and forecasts when a weekly window is empty or the provider blocks that model family.
- Adds a configurable grouping threshold for low weekly balances; this display setting does not disable accounts or discard usable quota.
- Adds all available Google text models, a dedicated Flash slot and distinct Flash reasoning variants to connected client menus, while retaining independent API models.
- Repairs approved Claude Desktop gateway routes after restart and keeps its fixed Haiku health probe separate from actual Google Haiku requests.
- Extends the Codex model catalog while preserving existing model entries and configuration backups.
- Adds provider and local-gateway checks in the API-key editor. Failed or cancelled draft checks preserve existing keys; checks use two short requests for the first model.
- Retains PySide6, five interface languages, themes and the callback fix. Client menus are updated through Connect applications with the owner's approval.

# Gemini Accounts 1.3.5 — Independent API keys

- Adds a separate API keys tab with encrypted profiles, add/edit/pause/remove controls, and per-key response, error and token statistics.
- Makes API models available alongside Google subscription models without replacing Google Gemini or Claude selections.
- Routes TokenHarbor requests through their original Anthropic or OpenAI endpoints and keeps Google account cooldowns separate.
- Migrates the existing local TokenHarbor key without embedding personal credentials in source code or executables.
- Preserves multiple model IDs when editing an API key instead of merging them into one line.
- Includes 142 passing tests and a successful streaming Haiku request through the installed gateway.

# Gemini Accounts 1.3.4 — Gateway retry handling and authenticated log uploads

- Removes the standalone Claude Agent SDK identity line from Anthropic system instructions before forwarding generation and token-count requests. User messages, tools and all other instructions are preserved. Both streaming and nonstreaming paths are covered by protocol tests; the affected remote installation has not yet been retested.
- Adds **Remove account** in account details, with confirmation. Deletes the saved credential and its local labels / verification state without deleting the Google account or enabling other paused accounts.
- Removes the exact experimental thought-summary override introduced in 1.3.2–1.3.3; custom payload settings remain intact.
- The gateway now keeps HTTP 429 retries local even when account cooldown metadata is missing or no longer matches the rejection. It sends keepalives, respects numeric Retry-After and otherwise uses increasing retry delays instead of exposing 429 to Claude's own retry loop. Authentication / verification failures still surface as errors.
- Claude token-count requests normalize the extended-context suffix before forwarding. Diagnostics record their route, original model, forwarded model and HTTP status as well as generation requests. This closes a diagnostics gap; it does not prove that the reported “model not found” error has been resolved.
- Nonstream response body byte counts are recorded correctly.
- **Send diagnostic log…** uses `https://logs.conch-labs.com/ingest`, POST `application/zip`, bearer authorization and `X-Filename: logs.zip`. A server connectivity test accepted a synthetic archive with HTTP 201. Upload credentials are stored encrypted per installation and are never included in published sources or diagnostic ZIPs. Enter an upload credential once when prompted; every upload still requires owner confirmation.
- Retains file log export and verified one-click Windows updates from 1.3.3. Install this version manually when upgrading from a version older than 1.3.3; later Windows updates can use **Routing statistics → Update to …**.

Google model availability and account restrictions remain outside the gateway's control. Waiting is cancellable; no assistant answers or tool calls are fabricated. This release does not claim to fix the underlying Google restriction or the unconfirmed model routing issue.

Windows: run `GeminiAccounts-Setup.exe` after current requests finish. Existing Google sign-ins and configuration backups are preserved. Terminal archives cover Windows x64, macOS Apple Silicon / Intel and Linux x64. See the [quick start](https://github.com/stasevboris/Gemini_Accounts#readme) and [terminal guide](https://github.com/stasevboris/Gemini_Accounts/blob/main/CLI.md).
