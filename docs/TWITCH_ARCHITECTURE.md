# Twitch Integration Architecture

## 1. Components

Split the Twitch integration into independent modules:

- `twitch_auth.py` - browser OAuth flow and Twitch account lookup.
- `twitch_credentials.py` - secure access-token storage.
- `twitch_bot.py` - Twitch IRC connection, message parsing, commands, and reconnects.
- `twitch_controller.py` - connects the UI/application lifecycle with auth and bot workers.
- `config.py` - non-secret settings such as username, target channel, command options, and cooldowns.

The OAuth access token must never be written to the regular JSON/config file or application logs.

## 2. Twitch Application Setup

Create an application in the Twitch Developer Console and configure a local redirect URI, for example:

```text
http://localhost:17846/auth/twitch/callback
```

Keep these values in one place:

```python
TWITCH_CLIENT_ID = "your-client-id"
OAUTH_PORT = 17846
REDIRECT_URI = f"http://localhost:{OAUTH_PORT}/auth/twitch/callback"
```

The redirect URI must exactly match the URI registered in Twitch.

## 3. OAuth Flow

1. The user clicks `Connect to Twitch`.
2. The app generates a cryptographically random `state` value.
3. A temporary HTTP server starts on `localhost:17846`.
4. The default browser opens Twitch authorization:

```text
https://id.twitch.tv/oauth2/authorize
  ?response_type=token
  &client_id=<client-id>
  &redirect_uri=<encoded-redirect-uri>
  &scope=chat:read+chat:edit
  &state=<random-state>
```

5. Twitch redirects to the local callback with the access token in the URL fragment.
6. Callback JavaScript reads the fragment and POSTs the token and `state` to the local app.
7. The app verifies `state` to protect against forged callbacks.
8. The app calls `GET https://api.twitch.tv/helix/users` with:

```http
Authorization: Bearer <access-token>
Client-Id: <client-id>
```

9. The returned Twitch login is stored in normal configuration; the token is stored separately in secure credential storage.
10. The temporary HTTP server is shut down. Add a timeout, for example two minutes.

The current BonkScanner implementation uses the implicit token flow. For a new long-lived application, consider Twitch's Authorization Code flow with PKCE if supported by the chosen deployment model.

## 4. Credential Storage

Preferred storage order:

1. Windows Credential Manager through `pywin32` (`win32cred`).
2. Python `keyring` as a cross-platform fallback.
3. If no secure backend is available, fail authorization instead of saving the token as plaintext.

Recommended interface:

```python
get_twitch_oauth_token() -> str
set_twitch_oauth_token(token: str) -> None
delete_twitch_oauth_token() -> None
```

On disconnect:

- Stop the IRC worker.
- Remove the token from credential storage.
- Clear the configured Twitch username.
- Attempt to revoke the token with `POST https://id.twitch.tv/oauth2/revoke` using `client_id` and `token`.

## 5. Twitch Chat Bot

No Twitch-specific bot library is required. The bot can use Python's standard `socket` and `ssl` modules and communicate directly with Twitch IRC over TLS:

```text
Host: irc.chat.twitch.tv
Port: 6697
```

After connecting, send:

```text
PASS oauth:<access-token>
NICK <authorized-username>
JOIN #<target-channel>
CAP REQ :twitch.tv/tags twitch.tv/commands
```

The authorized account and target channel may differ. This allows a dedicated bot account to join the streamer's channel. If no target channel is configured, default to the authorized username.

## 6. IRC Worker Responsibilities

Run the IRC connection outside the UI/main thread. The worker should:

- Establish a TLS socket connection.
- Authenticate and join the configured channel.
- Read data into a buffer and split complete messages on `\r\n`.
- Answer Twitch `PING` messages with `PONG`.
- Parse IRC tags, sender, command, channel, and message text.
- Handle `PRIVMSG` commands and send responses with `PRIVMSG #channel :message`.
- Enforce global and per-command cooldowns.
- Restrict commands using Twitch badges/tags when required.
- Close the socket cleanly when stopped.
- Reconnect after transient failures with a delay or exponential backoff.
- Never print the OAuth token in logs or error messages.

Requesting `twitch.tv/tags` allows access to badge and user metadata needed for moderator, VIP, and subscriber checks.

## 7. Application State

Safe values for ordinary configuration:

```json
{
  "username": "bot_account",
  "target_channel": "streamer_channel",
  "global_cooldown_seconds": 1,
  "command_cooldown_seconds": 5,
  "commands": {},
  "access_tier": "Everyone"
}
```

Keep runtime state, such as sockets, threads, reconnect counters, and command timestamps, in memory only.

## 8. Dependencies

Minimal dependencies for this architecture:

```text
requests     # Twitch Helix API calls
pywin32      # Windows Credential Manager
keyring      # optional cross-platform credential fallback
```

The IRC layer itself uses only Python standard-library modules: `socket`, `ssl`, `threading`, `http.server`, `webbrowser`, `secrets`, `json`, and `urllib`.

If the application already uses Qt, OAuth and IRC workers can be implemented as `QThread` classes with signals. Otherwise, regular `threading.Thread`, callbacks, events, or an `asyncio` implementation are sufficient.

## 9. Security Checklist

- Register an exact localhost redirect URI.
- Bind the callback server to `localhost`, not all network interfaces.
- Generate and verify a fresh OAuth `state` for every attempt.
- Limit callback request size and validate JSON/content type.
- Apply network timeouts to HTTP and socket operations.
- Store tokens only in OS-backed credential storage.
- Never commit client secrets or tokens.
- Never include tokens in logs.
- Revoke and delete the token during disconnect.
- Request only the scopes the application needs.

## 10. Suggested Startup Sequence

```text
Application starts
  -> load non-secret Twitch settings
  -> check secure storage for a token
  -> show Connected only when username and token both exist

User starts bot
  -> validate username, target channel, and token
  -> start IRC worker
  -> connect with TLS
  -> authenticate and join channel
  -> process chat until stopped
```
