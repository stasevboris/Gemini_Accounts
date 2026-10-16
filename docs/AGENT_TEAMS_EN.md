# Agent teams

Open **Team**, refresh accounts and create a roster. You can prepare and save the roster and settings while team mode is off. Choose an account, model, role and optional instructions for each participant. Mixed Google and ChatGPT rosters can use available models including `gpt-6-luna`. Accounts provide access and quota; agents provide separate sessions, histories and tool loops.

Choose exactly one coordinator and at least one worker. Dedicated reviewers are optional: other workers can review results. One participant requires review rounds to be zero. Expand **Task mode, limits and permissions**, describe the task and acceptance criteria, then check **Enable agent teams** beside the action buttons and choose **Start task**. The hint above the buttons explains why starting may be unavailable. Saving configuration does not start a task, and runs never resume automatically after restarting the app.

The coordinator decomposes the task; workers prepare results in parallel; independent reviewers check them and request revisions within the configured review rounds. The coordinator synthesizes the result. Unapproved or failed work is marked as needing review. Interrupted and budget-limited runs are not reported as complete.

Configure 1–100 participants separately from concurrent requests, overall provider request budget, runtime, tool steps, output length and review rounds. Temporary provider errors can be retried 0–3 times within the shared request budget; authentication failures are not retried. Sessions sharing an account share its quota and serialize requests. A larger team is not a guarantee of faster or better results.

Retries respect Retry-After and the selected account/model's native recovery cooldown. The board and chat show waiting progress; the stop button and overall time limit remain effective during that wait. Access and payment failures such as 401/402/403 require an available account or removing that participant. The selected credential is not silently replaced.

General tasks can use public web search and URL reading. Project mode adds bounded project-file tools. Workers and reviewers remain read-only. The coordinator can write reviewed final changes only when file writes are enabled, after checking the current file hash and preserving encrypted backups. Commands are a separate opt-in permission and run with the current user's permissions, with a 60-second process limit; use Git to track command-driven changes.

The UI provides a task board, peer feedback, activity journal, encrypted local history, stop controls and Markdown export. Closing the manager cancels a run started there; minimizing to the tray keeps it running. Chat-launched runs belong to the local gateway. Temporary account model prefixes pin requests to the selected credentials and are restored at the end. Recovery records survive crashes and are processed before another run. Accounts already using a custom prefix are not reconfigured automatically.

## Invoke a team in an existing Claude chat

Configure the roster, workspace, limits and permissions under **Team**, enable the feature and **Save settings**. Click **Connect team to Claude**. Connect the client under **Connections** first if needed. Restart Claude after its current work finishes to load the new configuration. Existing default models and other MCP servers are retained.

- Select the **Agent team** model in an existing conversation and send a task. The gateway supplies the conversation history included in that request as reference, then returns the team's result in the same chat. Switch back to any ordinary model afterwards.
- Keep the current model and ask it to delegate using the **gemini-accounts-team** MCP tools: `team_config`, `team_start`, `team_status`, `team_wait`, `team_stop`. The calling model must pass the relevant conversation context to `team_start`; the client may ask to approve tool use. If the model does not call tools, use the team model instead.

Neither route automatically reads other sidebar chats or the full Claude project history. Local files come from the project folder saved in the manager. Only one team can run at a time. Chat-launched runs appear in the manager's task board and can be stopped or exported there. They continue if the manager closes, but do not resume automatically after the gateway stops.

## Large files and documents

`read_file` reads text, code and DOCX by line; `read_text_chunk` reads by character offset. Follow `next_line` or `next_offset` to continue. `read_document` extracts PDF text by page and DOCX paragraphs/tables; `search_files` searches project text. Input files are limited to 50 MB. Image-only PDF scans require separate OCR; convert legacy DOC files first.

The supplied conversation is paginated through `read_chat_context`. Long agent histories are compacted into a continuation summary within the shared provider-request budget; full earlier messages remain in encrypted run history. Explicitly enabled coordinator commands are available during analysis and validation as well as final synthesis. Reviewed file writes retain their separate final-stage permission.



Google, ChatGPT and Claude accounts are supported. If a reviewer is unavailable, the team tries another independent account. At the tool-step limit, the agent gets a final tool-free turn to retain proposed changes and outstanding work. The shared request and time budgets still apply.
