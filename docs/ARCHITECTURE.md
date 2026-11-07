# Architecture

## Pipeline

```
 Ingestion            Storage              Stats / knowledge           Model            Product
 ─────────            ───────              ─────────────────           ─────            ───────
 Riot API (match-v5)  raw JSON lake  ──►  champion strength (Bayes)  ┐
 Data Dragon / CDragon (gz, immutable)    matchup & synergy deltas   ├─► draft value ──► search ──► API ──► UI
 Leaguepedia (pro)    DuckDB tables       timeline features          │   function        (picks,    (FastAPI) (web / overlay)
 League Client (live)                     champion attribute tags ───┘   (win prob)      bans)          ▲
                                          composition features                │                         │
                                                                              └── explanations ─────────┘
```

## 1. Ingestion

| Source | What | Status |
|---|---|---|
| Riot API match-v5 | Master+ solo queue matches + per-minute timelines | done (`drafter crawl`) |
| Data Dragon | champion ids, names, classes | done (`drafter static`) |
| CommunityDragon | full ability descriptions (input for tagging) | todo |
| Patch notes | buff/nerf signal for new patches | todo |
| Leaguepedia Cargo API | pro picks/bans/results, draft order | todo (pro phase) |
| League Client API (LCU) | live champion select state on the user's machine | todo (local only, no key needed) |

Rate limits are the main ingestion constraint. A dev/personal key is roughly 20 req/s and 100 req/2min **per regional host**, so one match + timeline is 2 requests, about 25 matches/min, ~36k/day per region. Crawling europe/asia/americas in parallel multiplies that. That's more than enough for Master+ (which only produces so many games per patch); the real pain is the dev key expiring every 24h.

## 2. Storage

- **Raw lake**: every API payload gzipped under `data/raw/{region}/{matches,timelines}/`. Never mutated, so any feature can be recomputed without re-crawling.
- **DuckDB**: parsed tables (`matches`, `participants`, `bans`, `players`) for fast aggregation. Single file, no server.
- Rough size: ~10 KB per match, ~80 to 100 KB per timeline gzipped, so ~10 GB per 100k matches with timelines.

## 3. Stats layer

Model everything in **log-odds space** so effects add up and stay interpretable.

- **Champion strength** per (patch, role): Bayesian shrinkage. Prior = previous patch estimate (decayed) + patch-note adjustment; likelihood = this patch's games. Fixes the cold start on patch day and stops 30-game samples from looking broken.
- **Matchup delta** (lane opponent, and cross-lane where it matters): residual win rate *after* accounting for both champions' individual strengths. Pooled across patches since matchups move much less than raw strength.
- **Synergy delta** (ally pairs): same idea, residual over individual strengths.
- **Timeline features** per matchup: gold/xp diff at 10/15, first-blood and solo-kill rates, jungle proximity, win rate by game length bucket. These power the "why" (wins lane but falls off, gank-dependent, etc.).

## 4. Knowledge layer: champion attributes

A versioned file in the repo (`data/tags/champions.yaml`, reviewed in PRs):
frontline, engage, disengage, peel, poke, waveclear, hard CC, AD/AP/true split, scaling curve, split push, mobility, range.

Workflow: LLM drafts scores from CommunityDragon ability text → human review (game knowledge) → re-run only for reworked or new champions.

Composition features are aggregates of these (e.g. `frontline_total`, `ad_share`, `engage_max`) and get **validated against win rate**. A warning like "no frontline" is only shown if it actually costs games in the data.

## 5. Draft value function

`P(blue wins | 10 champions + roles)`. Start with a regularized logistic model over strength + matchup + synergy + composition terms (few parameters, transparent, robust to noise). Try gradient boosting later only if it beats it.

Evaluation, always time-based (train on earlier games, test on later ones):
- log loss and calibration (a 55% prediction should win 55% of the time)
- expected ceiling in solo queue: ~53 to 56% accuracy, because player skill dominates. That's fine, the goal is ranking choices, not predicting games.
- playtesting: does it make sense to a real player?

## 6. Search

Draft is a two-player sequential game. At each step:
- candidates = champions not banned/picked, filtered by plausible roles
- evaluate future states with the value function, opponent responses from an **opponent model** (what's likely to be picked: pick rates in solo queue, pro priority later)
- depth-limited expectimax first, MCTS if needed

This is what gives real ban logic (deny the opponent's best answer), blind-pick safety, and flex value. Fearless series planning (pro phase) extends the same search across games.

## 7. Explanations

Every recommendation decomposes into its log-odds terms (strength, each matchup, each synergy, composition), which map to factual sentences: "+2.1% from beating Darius in lane (+450 gold @15)", "team was 85% AD, this adds magic damage". An LLM can rephrase those facts into readable text, but never invents them.

## 8. Product

- **Backend**: FastAPI exposing `/recommend` (draft state → ranked picks/bans + explanations).
- **Frontend**: web UI (draft board), later a desktop companion that reads live champion select from the League Client.
- All stats precomputed per patch, so recommendation is fast (milliseconds) and works offline.

## External needs

| Need | Required? | Cost |
|---|---|---|
| Riot API key | yes. Dev key to start, apply for a **personal key** (doesn't expire). Production key only if the tool goes public (needs Riot approval + policy compliance). | free |
| LLM API (e.g. Claude) | offline only: champion tagging (one-off, ~170 champions), patch-notes parsing (each patch), optional explanation phrasing. Not on the hot path. | a few dollars total |
| GPU | no, models are small | - |
| Hosting | not until public; everything runs locally | - |
| Pro data | Leaguepedia API, free, rate-limited | free |
