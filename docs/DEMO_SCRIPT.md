# VideoMind demo script (5 minutes)

Rehearse it twice. **Warm the backend five minutes before** — hit
`GET /api/health` so the free-tier instance is awake (see cold-start note in the
[README](../README.md)). Demo on the seeded videos so nothing depends on live
YouTube fetching.

| Time | Beat | What you say |
|---|---|---|
| 0:00 | Paste a seeded technical talk | "One link in. Watch the pipeline — those aren't fake progress bars, each is a LangGraph node." |
| 0:40 | Point at a retry in the timeline | "Segmentation produced overlapping chapters. A deterministic verifier caught it and repaired the boundaries without a second LLM call. If repair hadn't worked, it would re-prompt — but only then." |
| 1:20 | Scroll the chapter rail | "Chapter heights are proportional to real duration, so the rail is a map of the video. Titles and summaries are structured Pydantic output, batched six at a time to stay inside the free tier." |
| 2:00 | Ask a question needing synthesis across two chapters | "The grader scored the first retrieval as insufficient, so the planner escalated from a direct rewrite to decomposition. Same graph, different path." |
| 2:30 | Ask something the video never covers | "The grader scored every retrieved chunk as irrelevant, so the system declined instead of guessing. An honest 'I don't know' is a feature, not a gap." |
| 2:50 | Open the trace panel | "Twelve chunks retrieved, five kept, one citation dropped because the model referenced a chunk id that wasn't in the retrieved set — the validator removed it rather than showing a fabricated timestamp." |
| 3:30 | Click a citation | "Timestamps come from chunk metadata, never from the model. A hallucinated citation is structurally impossible here." |
| 4:00 | Open Settings, switch to their provider, paste their key, re-ask | "Nothing recompiles. Every agent talks to one adapter interface. Your key is used for that request and never stored." |
| 4:40 | Close | "Nine agents, two graphs, one deterministic guardrail layer between every LLM stage." |

## Pre-demo checklist

- [ ] Backend warmed (`GET /api/health` returns 200) within the last 5 minutes.
- [ ] Seeded demo videos present (`videos_cached ≥ 3` in the health payload).
- [ ] A spare provider key on hand for the "switch provider" beat.
- [ ] `scripts/e2e_smoke.py` run green against the deployed URL earlier that day.
- [ ] One question prepared that spans two chapters; one the video never covers.
