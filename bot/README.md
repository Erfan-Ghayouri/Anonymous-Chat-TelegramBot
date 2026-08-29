# ChatoChi — Anonymous Chat Telegram Bot

A production-ready Persian-language anonymous two-person chat Telegram bot built on
**Pyrogram** (via the `kurigram` fork) and **PostgreSQL**.

The bot allows users to:

- Create and edit an anonymous profile with a separate internal ID (`#482731`)
- Search for anonymous partners (random, gender-filtered, city-filtered)
- Use **Premium Search** for higher matchmaking priority (coin-based)
- Enter an **anonymous two-person chat session**: every message (text, photo,
  video, voice, audio, document, sticker, GIF) sent by either user is **automatically
  relayed** to the other participant — there is **NO Direct Message button**
- Skip / Block / End / Report the current partner
- Use a coin wallet (signup bonus + referral rewards + admin adjustments)
- Invite friends and earn coins per successful invite
- View help/guide in Persian
- Admins: stats, broadcast, coin adjustments, user moderation, sponsor-channel mgmt

## Architecture

The project keeps a clean separation of concerns:

```
bot/
├── main.py                # entry point — wires everything together
├── config.py              # centralized env-driven configuration
├── requirements.txt
├── .env.example
├── database/
│   ├── __init__.py
│   └── db.py              # ThreadedConnectionPool + all tables + CRUD
├── handlers/              # Pyrogram handlers (one per feature area)
│   ├── start.py           # /start with referral processing
│   ├── help.py            # /help + main-kb Guide button
│   ├── profile.py        # 👤 My Profile view/edit (FSM)
│   ├── search.py          # 🔎 Anonymous Search + ⭐ Premium
│   ├── chat.py            # chat controls + message relay (THE core)
│   ├── wallet.py          # 💰 Wallet balance + history
│   ├── referral.py        # 🎁 Invite Friends
│   ├── settings.py        # ⚙️ Settings + blocked list
│   └── admin.py           # admin commands + inline panel
├── services/              # business logic (no Pyrogram awareness)
│   ├── users.py           # user/profile operations
│   ├── matchmaking.py     # race-safe matchmaking engine + poller
│   ├── chat.py            # chat session + anonymous relay
│   ├── wallet.py          # atomic coin operations
│   ├── referral.py        # referral processing
│   ├── reports.py         # report creation with cooldown
│   ├── blocks.py          # block storage
│   └── sponsors.py        # EXISTING sponsor gate (preserved)
├── utils/
│   ├── keyboards.py       # all Persian reply + inline keyboards
│   ├── states.py          # in-memory FSM
│   ├── validation.py      # input validation + Persian city list
│   ├── persian.py          # display helpers (gender/balance labels)
│   └── rate_limit.py       # per-user rate limiter
└── tests/
    ├── conftest.py        # fixtures + PG availability check
    ├── test_unit.py       # 18 pure unit tests (always run)
    ├── test_db.py         # 17 integration tests (need PG)
    └── test_relay.py      # 3 relay integration tests (need PG)
```

### Why `copy_message` for the relay?

`copy_message` re-sends a message to the partner's chat with the **bot** as the
sender. It does NOT include a "forwarded from" header — so the partner sees a
fresh message and the original sender's Telegram identity is never leaked. This
is the recommended approach for anonymous relays.

## Database schema

Tables created by `Database.create_tables()` (idempotent — safe to call on
existing installs; new columns added with `ADD COLUMN IF NOT EXISTS`):

| Table | Purpose |
|---|---|
| `users` | Telegram users with internal_id, profile, wallet balance, status, premium_until, etc. |
| `sponsor_channels` | Existing — sponsor channel gate |
| `blocked_users` | `(blocker_id, blocked_id)` unique |
| `referrals` | One row per referred user; `referred_id` is UNIQUE so rewards are idempotent |
| `chat_sessions` | `(user_a, user_b, status)` with two partial unique indexes ensuring one active session per user |
| `search_filters` | Per-user saved search preferences |
| `search_queue` | In-flight matchmaking queue |
| `wallet_transactions` | Append-only ledger of every wallet mutation |
| `reports` | Reports with status (`open` / `resolved`) |
| `bot_settings` | Key/value config overrides |

## Race safety

- **Matchmaking**: `find_match` runs entirely inside a single transaction, uses
  `SELECT ... FOR UPDATE` on the user's search_queue entry and `FOR UPDATE OF q
  SKIP LOCKED` on candidate rows, and the `chat_sessions` table has TWO partial
  unique indexes (`WHERE status = 'active'`) — one keyed by `user_a`, one by
  `user_b` — so concurrent inserts cannot create two active sessions for the
  same user.
- **Wallet**: `adjust_wallet_atomic` uses a single conditional UPDATE that
  refuses to let the balance go negative; the resulting balance is captured in
  `RETURNING wallet_balance` and recorded as `balance_after` in the same
  transaction, so the ledger and balance are always consistent.
- **Referrals**: `referred_id` is UNIQUE, so duplicate referrals are rejected
  by the DB itself.
- **Blocks**: `PRIMARY KEY (blocker_id, blocked_id)` makes blocks idempotent.

## Configuration

All configurable values live in `config.py` and are loaded from `.env`:

| Variable | Default | Notes |
|---|---|---|
| `API_ID` | — | from https://my.telegram.org |
| `API_HASH` | — | from https://my.telegram.org |
| `BOT_TOKEN` | — | from @BotFather |
| `BOT_USERNAME` | — | without leading @ |
| `DATABASE_URL` | — | e.g. `postgresql://user:pass@localhost:5432/chatochi` |
| `ADMIN_IDS` | — | comma-separated list of Telegram user IDs |
| `ADMIN_ID` | — | legacy single-admin fallback (still works) |
| `NEW_USER_BONUS` | 5 | coins granted on first /start |
| `REFERRAL_REWARD` | 20 | coins granted to the referrer |
| `PREMIUM_SEARCH_PRICE` | 50 | cost of premium search activation |
| `PREMIUM_SEARCH_DURATION_MIN` | 30 | minutes of premium priority |
| `REPORT_COOLDOWN_SEC` | 60 | min seconds between reports |
| `SEARCH_COOLDOWN_SEC` | 3 | min seconds between search attempts |
| `MSG_PER_MIN_LIMIT` | 60 | max relayed messages per minute per user |
| `MAX_SEARCH_QUEUE_SECONDS` | 120 | search timeout |
| `ENABLE_SPONSOR_CHECK` | 1 | toggle the sponsor-channel gate |

## Installation

```bash
# 1. clone
git clone <your-repo-url> bot
cd bot

# 2. virtualenv
python3 -m venv venv
source venv/bin/activate

# 3. deps
pip install -r requirements.txt

# 4. configure
cp .env.example .env
# edit .env and fill in API_ID, API_HASH, BOT_TOKEN, BOT_USERNAME, DATABASE_URL, ADMIN_IDS

# 5. database (schema is created automatically on first run, no manual migration needed)
createdb chatochi  # if not exists

# 6. run
python main.py
```

## Admin commands

| Command | Description |
|---|---|
| `/admin` | open the inline admin panel |
| `/stats` | quick stats summary |
| `/broadcast <text>` | broadcast a text to all users |
| `/adjust <user_id> <amount>` | adjust a user's coin balance |
| `/userinfo <user_id>` | show user info |
| `/ban <user_id>` | ban a user (sets status=banned, ends active session) |
| `/unban <user_id>` | unban a user |
| `/addchannel <channel_id> <invite_link>` | (existing) add sponsor channel |
| `/deletechannel` | (existing) list & delete sponsor channels |

When you click the **«پیام همگانی»** button in `/admin` panel, you can send
any message (text, photo, video, …) and the bot will `copy_message` it to
every user in chunks.

## Tests

```bash
# pure unit tests — always runnable, no DB needed
python -m pytest tests/test_unit.py -v

# integration tests — need PostgreSQL
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test_db \
  python -m pytest tests/ -v
```

The test suite covers:

- Input validation (name / bio / age / city)
- Persian display helpers
- FSM state store + cleanup
- Rate limiter (within-limit, separate keys)
- Referral payload parsing + link building
- Self-referral prevention
- Idempotent referral rewards
- User creation grants signup bonus
- Idempotent signup (no double bonus)
- Wallet double-spend prevention
- Wallet credit + transaction recording
- Block creation + idempotency
- Matchmaking: self-match prevention
- Matchmaking: session creation
- Matchmaking: blocked users skipped
- Matchmaking: gender filter respected
- Matchmaking: double-match prevented (concurrent threads)
- Referral processing grants reward
- Report creation + cooldown rate limit
- **Message relay: no active session -> no relay**
- **Message relay: delivers to partner in both directions**
- **Message relay: message after session ends -> NOT relayed**

## Chat behavior — the core feature

When two users are matched:

1. Both receive the «🎉 یک نفر پیدا شد!» card with **inline-only** chat controls:
   - ⏭ شخص بعدی (Next)
   - 🚫 مسدود (Block)
   - ❌ پایان گفتگو (End)
   - 🚨 گزارش (Report)
2. **There is no Direct Message button anywhere in the bot.**
3. Every message sent by either user is forwarded via `client.copy_message`
   to the partner's chat. The relay:
   - Detects whether the sender has an active session
   - Validates the session is still active
   - Relays text, photos, videos, voice, audio, documents, stickers, GIFs
   - Ends the session if the partner has blocked the bot
   - Handles Telegram API errors (FloodWait, RPC errors)

## Limitations / known issues

- FSM is in-memory; restarting the bot loses in-progress flows (bio entry,
  report reason entry). Persistent flows (chat sessions, wallet, blocks)
  live in the DB and survive restarts.
- Search filters are stored per-user in `search_filters`; only one saved
  filter set per user.
- The message relay doesn't preserve `reply_to_message` quoting across users
  (a quote references a message ID in the original chat, which is meaningless
  in the partner's chat).
- The blocked-list view in Settings shows the most recent 20 entries.
- Concurrent matchmaking is correct under PostgreSQL's default isolation,
  but extremely high concurrency may benefit from raising the pool size
  (`Database(url, maxconn=N)`).

## License

Independent implementation. No third-party branding, logos, or proprietary
text is used.
