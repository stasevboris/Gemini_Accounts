# API keys and Google subscriptions

**English** · [Русский](TOKENHARBOR_RU.md) · [Back to the README](../README.md)

The Windows desktop **API keys** tab manages TokenHarbor and Anthropic-compatible
HTTPS providers separately from Google subscription models.

## Add a profile

1. Open **API keys → Add API key**.
2. Choose a name and provider protocol, then enter the HTTPS base URL and key.
3. Enter one model ID per line. **Load provider models…** can add a selected ID
   from the provider's catalog; repeat it to add more models.
4. Save. Reopen Claude Desktop to refresh its model menu.

Profiles appear as `API · profile name · model`, alongside Google Gemini and
Google Claude. Each profile uses `api/<profile>/<model>` internally. Two keys to
the same model remain separate, and do not replace the Google model selections.

## Edit, pause or remove

An empty key field keeps the saved key. Model IDs remain on separate lines.
Pausing hides the profile's models from the catalog and prevents new requests
through it. Removing a profile deletes its saved key and models.

The gateway reads profile changes on new requests; changing a key does not
require restarting the gateway. A client may still need to reload its model menu.

## Usage statistics

Each key shows response/error counts, input/output tokens, average duration,
the last model and response status. Retries count as provider attempts. Input
tokens include cache usage when the provider reports it. Statistics do not
calculate a remaining quota or balance, and do not store conversation content.
An interrupted successful HTTP response is recorded as error 499.

## Storage and request formats

Windows stores the registry in `api-keys.dpapi` under the app's local data folder,
protected by DPAPI. It is separate from the source checkout and release files.
The previous `tokenharbor-key.dpapi` is read as an initial profile and migrated
when a profile is saved. A removed profile does not reappear from the old file.

The gateway preserves the request format: `/v1/messages` remains Anthropic;
`/v1/chat/completions` and `/v1/responses` remain OpenAI. TokenHarbor supports both
formats. Native Anthropic-compatible profiles use `x-api-key`. A provider with
only OpenAI endpoints requires an Anthropic adapter for Claude Desktop.

Google account cooldowns do not block independent API models. A key's own
provider can still reject a request or impose its own rate limits.

Provider reference: [TokenHarbor API](https://tokenharbor.ai/docs/api/curl).
# Connection checks

The key editor can check the first model with two short requests: directly at the
provider and through the local gateway. Draft edits are not saved by the check;
existing keys remain available while it runs. Failed checks restore the previous
encrypted registry. Changed connections are checked before saving by default;
you can turn this off to store a connection while the provider is offline.
