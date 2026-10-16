# Gemini Accounts: Windows guide

Gemini Accounts manages your accounts and API keys and connects available models to Claude Desktop, Claude Code and Codex. Subscriptions, accounts and API credit are separate. Your provider determines access to each model.

## 1. Install

1. Extract the supplied archive into a separate folder.
2. Run `GeminiAccounts-Setup.exe` and finish installation. Python is not required.
3. Open Gemini Accounts using the shortcut.
4. Install Firefox for ChatGPT and Claude sign-in. These buttons open a regular browser tab.

Before updating, wait for active generations to finish. The installer preserves saved sign-ins and API profiles. Do not delete the data folders to update the application.

## 2. Google accounts

1. Click **Add Google account**.
2. Sign in in the browser and approve the requested permissions.
3. Return to the manager and wait for the account and quota data.
4. Repeat for your other accounts. Choose **Use all · automatic routing** to use the enabled pool.

Gemini and Google-provided Claude quotas are separate. Remaining percentages do not guarantee access to every model. Check the selected model and the latest request result.

## 3. API keys

1. Open **API keys → Add API key**.
2. Enter a profile name, provider, API URL and your key.
3. Load the provider catalog or enter exact model IDs, one per line. A marketing name may differ from its API ID.
4. Click **Test key and model**, then save the profile.
5. Add other keys the same way. Their models remain separate from Google subscription models.

API statistics show attempts, errors, token usage and response time, not your provider balance. Compatible enabled keys with the same API URL and exact model ID can provide fallback before response content is delivered. Disable this option in the key editor if desired.

## 4. ChatGPT accounts

1. Open **ChatGPT → Add ChatGPT account**.
2. Finish signing in in Firefox and wait for confirmation in the manager.
3. To add another account, switch the ChatGPT login in the browser and repeat.
4. Alternatively choose **Import auth.json** and explicitly select a Codex file containing a ChatGPT sign-in. Your existing Codex credentials are not imported automatically.

ChatGPT has a separate account pool. Google quota and priorities do not control GPT access. If the provider offers a quota reset, using it requires confirmation and may consume one available reset.

## 5. Claude subscription accounts

1. Open **Claude → Add Claude account**.
2. Sign in with your own account in Firefox. Your subscription must allow the requested access.
3. Wait for the automatic callback. If it fails, paste the authorization code or callback URL into the login dialog and click **Complete sign-in with this code**.
4. You can also explicitly import a Claude OAuth JSON export or a Claude Code credentials file with complete OAuth tokens. Existing application credentials are not imported automatically.
5. **Test response** sends a small request pinned to that account and consumes a small amount of quota.

Claude subscription accounts use their own pool. Their client models are labeled `Claude subscription`, separate from Google-provided Claude and API-key models. Usage data is cached for five minutes. An Opus- or Sonnet-specific weekly limit does not imply that every model is exhausted.

ChatGPT and Claude support is new in this build and covered by automated tests. Verify sign-in and generation using your own accounts separately: provider restrictions or interface changes can affect availability.

## 6. Connect a client

1. Install your client: Claude Desktop, Claude Code CLI or Codex.
2. Click **Connect applications**, select the client and approve the proposed configuration changes.
3. Wait for active work to finish, then reopen the client to load the updated configuration and model list.
4. In Claude Desktop use the **Code** tab with the configured local preset. Regular Claude web chats use a separate connection.
5. Select a model by its source and send a test prompt: “Write a Python function that removes duplicates from a list while preserving order. Include three examples.”

Source labels:

- `Gemini · …`: Google accounts.
- `Claude · …`: Claude through Google.
- `API · Profile name · …`: your API key.
- `ChatGPT · …`: ChatGPT accounts.
- `Claude subscription · …`: your own Claude subscription accounts.

You can change models within a conversation when the client passes conversation history to the newly selected model. The manager does not transfer chats between separate applications. Switching providers sends the accumulated history to the selected provider. Attachment and tool support depend on the model and client.

## 7. Everyday use

- Keep the manager open for monitoring and automatic routing.
- Do not close a client during generation if you want the response to finish.
- Paused accounts are excluded from automatic selection.
- Removing an account deletes its saved local sign-in, not the account at the provider.
- Hide account names in the account-list settings before capturing screenshots.

## 8. Troubleshooting

**429 / Rate limit:** provider request-rate or quota restriction. Check the latest event and reset time. Another account helps only if it can access the same model.

**401:** invalid authorization or key. Check the API key or sign in again.

**402:** provider billing refusal. Check balance and model access with the provider.

**403:** access refused. Check permissions, verification requirements and model availability.

**502 / 503:** temporary provider or local-service error. Check the log and retry after the cause is resolved.

**Saved key but no client model:** verify that the profile is enabled and the exact model ID is saved. Refresh the connection and reopen the client after active work finishes.

**Missing quota:** the provider may not return usage data or may restrict quota reads. The manager does not invent percentages. Check actual response availability.

**Firefox not found:** install Firefox and start sign-in again.

**Local connection returned error:** verify that the manager and local services are running. Do not delete saved accounts or reset data before diagnosing the issue.

## Websites and search in Claude Desktop

Send a URL and ask the model to read the page, or ask it to search the web. The managed Desktop profile allows website access. Manually configured host rules are preserved.

For a model without native search, a separate WebSearch call uses an available Gemini or ChatGPT model and returns the results to the main model in the same conversation. A connected, available Google or ChatGPT account is required, and search may use its quota.

After updating an older profile, start a new Desktop conversation: existing sessions retain their previous network settings. Websites that require your sign-in or reject automated requests may still be inaccessible.

## 9. Data and help

Windows data lives in `%LOCALAPPDATA%\GeminiAccounts` and `%LOCALAPPDATA%\ClaudeGemini`. Saved sign-ins, keys and full backups contain secrets. Do not publish them or send passwords and keys to the seller in chat.

The manager backs up client settings before changing them. **Connect applications → Restore previous settings** restores those saved configurations; later manual client edits may be replaced.

When asking for help, include the application version, client, model source and ID, error time and status code. Hide email addresses, keys and private conversations in screenshots. Inspect diagnostic archives before sharing them.

If your order includes setup assistance, arrange it through FunPay chat. The build-and-guide package is for self-service installation. The software is open source; support scope and duration follow your order description.

## Priority, reserves and compact view

The ↑ counter sets account priority from 0 to 999: larger values go first among available accounts. Equal values retain automatic ordering. A high priority does not bypass provider restrictions.

Drag the thin marker on each quota track, or double-click to enter a percentage. A 20% reserve stops future requests at 20% remaining; it does not mean spending only 20%. Set 0% to remove the reserve. Settings are separate for each account, model family and window. Missing measurements hold a configured reserve until refreshed. An active response may cross the boundary before the next measurement. Paid extra usage is not enabled.

Click the arrow beside account lists or pooled quota summaries to collapse them. Compact indicators remain: gray means missing data and red means zero remaining. The header gear is available in compact mode and opens language, theme, privacy and service visibility options. Hidden services keep their sign-ins, routing and quota monitoring.

## Token estimates and notifications


The calculator in **Routing statistics** estimates tokens for a chosen quota share after three clean measurements. The forecast below estimates time to the reserve and compares it with the reset time. Both depend on workload and are approximate, rather than guaranteed budgets. Historical requests loaded at startup are excluded from new usage intervals.

Display settings let you enable sign-in and quota-reserve notifications separately. Repeated polling of the same condition does not repeat an alert. Credential uptime reports observed authorization availability; manual pauses and transient network failures do not disable accounts.

For Google sign-in from another browser profile, copy the authorization link from the sign-in dialog. If that browser blocks the local redirect, paste the complete callback address into the same dialog. A rejected address can be retried without starting a new login.

## Compact Claude model menu

The Google section lists Opus/Sonnet once and Flash 3.8 High, Medium and Low. Other Flash/Pro/Lite generations and Google Haiku are hidden from this picker. GPT and connected API/provider entries remain separate. Claude Code 2.1.242 or newer supports the explicit lineup. Refresh the connected client configuration and restart the client after finishing active work. Opus/Sonnet retain the client effort controls; Flash variants are separate model IDs. Existing conversations keep their original routes.


## Agent teams

On startup, the manager loads fresh Google quotas and sends a short background “Hi” to full weekly quota groups. Each request is pinned to its account without changing the current chat. Pauses, access restrictions and quota reserves remain respected, and persistent cooldowns prevent repeated greetings after a restart. Probes use an available Flash Low or GPT-OSS model for the relevant group. Weekly buckets already in use do not need an extra startup probe. Account tooltips distinguish an HTTP response from observed weekly consumption. Google controls quota timers; the manager does not report activation until refreshed quota data supports it.

Use the Team tab to enable and configure collaborative agents: accounts, models, roles, concurrency, reviews and limits. Saving settings does not start a task. Google, ChatGPT and Claude accounts are supported. See docs/AGENT_TEAMS_EN.md in the project repository.

To invoke the roster in an existing chat, save its settings and click **Connect team to Claude**. Restart Claude after its current work finishes. Select the **Agent team** model or ask the current model to call MCP tool `team_start` with the task and relevant context. Progress, stopping and export are available in Team. Other chats are not read automatically. Text, code, DOCX and text-based PDF files are paginated; coordinator project commands require a separate permission.

## Flua and other API keys

Open **API keys → Add API key**. Choose **Flua · Anthropic** to prefill `https://api.flua.ink` and `claude-opus-5-5`, enter your key and test the connection. Available models depend on that key's permissions; model discovery fetches its available IDs. For another Anthropic-compatible endpoint, select the generic option and provide its API host, key and models. Re-enter the appropriate key when changing servers. Testing or saving a key does not start an agent team.

## API key rotation

Enable rotation on compatible profiles with the same API URL, protocol and model ID. A failed request can switch keys before response content is delivered. Other endpoints are never selected automatically. Unavailable keys are skipped until the retry time shown in their cards. HTTP 429 without an explicit quota-exhaustion error is displayed as temporary request throttling.
