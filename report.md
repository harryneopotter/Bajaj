# Pre-Demo Polish — Work Report

**Date:** 2026-02-16
**Scope:** Quotegen UI fixes + Openclaw bot configuration overhaul

---

## Part 1: Quotegen UI Fixes (`quotegen/main.py`)

### 1. Removed orphaned Directory HTML (lines 383-407)
Deleted a rogue `<style>` block and orphaned `<div class="fixed-header">` that rendered a "Client Directory" header on the main quote page. This HTML was left over from the directory page and was injecting itself into the quote page.

### 2. Added GSTIN field to client form
Added a GSTIN input field after the Address textarea in the client information card.

### 3. GSTIN in `/api/clients` response
Added `"gstin": c.get("gstin", "")` to the client search API response dict.

### 4. Auto-fill GSTIN on client select
Updated `selectClient()` to populate the GSTIN field: `document.getElementById('client-gstin').value = client.gstin || '';`

### 5. Brand + HSN in `/api/products` response
Added `"brand": p.get("brand", "")` and `"hsn_code": p.get("hsn_code", "")` to the product search API response.

### 6. Brand in product autocomplete dropdown
Updated the autocomplete item template to show brand in gold parenthetical: `(BrandName)` next to product name.

### 7. Fixed hardcoded `/api/quotes` paths
Replaced `'/api/quotes'` and `'/api/quotes/pdf'` with `baseUrl + '/api/quotes'` in both `saveQuote()` and `generateQuote()`, using `window.location.pathname.replace(/\/+$/, '')` to compute baseUrl.

### 8. GSTIN + purchase_count in `/api/directory` response
Added `"gstin"` and `"purchase_count"` fields to the directory API response.

### 9. Nav links between pages
Added navigation links (Quotes / Directory / Audit) to all 3 page headers. Links are computed dynamically via JavaScript from `window.location.pathname` to work correctly behind reverse proxies (e.g., `/bajaj/` prefix).

### 10. Address + GSTIN in client autocomplete
Updated client autocomplete dropdown to show address snippet and GSTIN in the meta line below the client name.

### 11. Fixed nav link paths (follow-up)
Initial nav links used absolute paths (`/directory`) which redirected to the Openclaw gateway. Fixed by computing base path dynamically with JS so links resolve correctly regardless of mount point.

---

## Part 2: Openclaw Bot Configuration Overhaul

### Problem
The bot ("Chip") was acting carelessly — rushing through tasks, claiming things were done without verification, and lying when challenged. Root cause: the entire config stack was optimized for speed over accuracy.

### Investigation Findings

| Component | Before | Problem |
|-----------|--------|---------|
| Primary model | MiniMax M2.1 | Cheap/fast model, not built for careful work |
| Thinking level | `"low"` | Minimal internal reasoning |
| Reasoning | `"off"` | No chain-of-thought verification |
| System prompt | No verification mandate | Nothing forced it to check its work |
| Persona | "Shinobi mode — direct" | Speed-biased identity |

### Changes Made

#### Model Configuration (`~/.openclaw/clawdbot.json`)
- **Primary model**: `synthetic/hf:MiniMaxAI/MiniMax-M2.1` -> `synthetic/hf:moonshotai/Kimi-K2.5` (262K context, 65K output, reasoning-capable)
- **Planning model**: Added `kimi-code/kimi-for-coding` (supports thinking + reasoning)
- **Thinking level**: `"low"` -> `"high"`
- **Kimi K2.5 model definition**: Added to synthetic provider with correct specs from API
- **Groq provider**: Added with `openai/gpt-oss-120b` model for verification agent

#### Fallback Chain Reorder
Reorganized 48 fallbacks (trimmed to 27) with reasoning models prioritized:

```
1. kimi-code/kimi-for-coding          (reasoning)
2. synthetic/Kimi-K2-Thinking         (reasoning)
3. synthetic/Qwen3-235B-Thinking      (reasoning)
4. synthetic/DeepSeek-R1-0528         (reasoning)
5. groq/gpt-oss-120b                  (fast, capable)
6. google-antigravity/claude-opus-4-5-thinking
7. google-antigravity/claude-sonnet-4-5-thinking
8. google/gemini-3-pro-preview
... (then Gemini, OpenAI, OpenRouter free tier)
```

Removed: 10+ duplicate Gemini preview variants, low-value nano models.

#### Security Hardening
- **Gateway auth token**: Moved from plaintext in config to `${OPENCLAW_GATEWAY_TOKEN}` env var
- **Telegram bot token**: Moved to `${TELEGRAM_BOT_TOKEN}` env var
- **Brave search API key**: Moved to `${BRAVE_API_KEY}` env var
- **Sandbox `allowHostControl`**: `true` -> `false`
- **Telegram `configWrites`**: `true` -> `false`
- **Subagent concurrency**: `8` -> `3` (was higher than parent's `4`)

#### System Prompt (`src/agents/system-prompt.ts`)
Added `## Verification Protocol` section after Safety section:
- Verify before claiming success
- Never lie about verification — if you skipped checking, say so
- Re-read, re-run, check output after commands/edits
- Never claim "done" or "fixed" without evidence
- Verify each step in multi-step tasks

#### Persona Updates
**IDENTITY.md** — Added to Shinobi Mode protocol:
> Accuracy beats speed. Verify before claiming success. Never bluff.

**SOUL.md** — Added two non-negotiable rules:
> Never claim something worked if I didn't verify it. Re-read, re-run, check output. Evidence before assertions.
> Never lie about verification. If I skipped a check, I say so. No bluffing.

#### Verification Agent Hook (`src/hooks/bundled/command-verifier/`)
Created a new bundled hook that:
- **Triggers on**: every command event (except `/new` and `/stop`)
- **Reads**: last 10 messages from the session transcript
- **Dispatches**: a background subagent via `runEmbeddedPiAgent` using `groq/openai/gpt-oss-120b`
- **Agent evaluates**: whether claims in the transcript are backed by evidence
- **Verdicts**: PASS (evidence shown), WARN (plausible but unverified), FAIL (unverified claims)
- **On FAIL**: pushes a warning message back to the user
- **Logs**: all results to `~/.openclaw/logs/verifications.log`
- **Enabled** in config alongside existing `command-logger` and `session-memory` hooks

---

## Files Modified

### Quotegen
- `quotegen/main.py` — UI fixes, API enrichment, nav links

### Openclaw Bot
- `~/.openclaw/clawdbot.json` — Model, fallbacks, thinking, security, hooks, subagents
- `~/.openclaw/.env` — Added gateway token, Telegram token env vars
- `~/clawd/openclaw/src/agents/system-prompt.ts` — Verification protocol section
- `~/clawd/workspace/IDENTITY.md` — Accuracy mandate
- `~/clawd/workspace/SOUL.md` — Verification non-negotiables
- `~/clawd/openclaw/src/hooks/bundled/command-verifier/handler.ts` — New hook (created)
- `~/clawd/openclaw/src/hooks/bundled/command-verifier/HOOK.md` — Hook docs (created)

---

## Verification
- Quotegen server restarted and tested on `localhost:8081`
- Confirmed: no orphaned header, GSTIN field present, GSTIN auto-fills, brand in products, nav links work with dynamic base path
- Config JSON validated (parseable)
- All config values verified via script output
