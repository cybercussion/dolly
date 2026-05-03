# Dolly Blink AI — Local Vision Analysis Plan

## Problem

Blink cameras are "dumb" motion detectors. Unlike Wyze (which provides tags like `person`, `vehicle`, `pet`), Blink events arrive with zero context — just "motion detected." Every rustling branch, passing car headlight, and neighborhood cat triggers the same priority notification. This makes Blink alerts noisy and easy to ignore, which defeats the purpose.

## Idea

Run Blink snapshots through a local vision model (Gemma 3 27B via Ollama) to generate a short scene description and object tags before sending the notification. The notification goes from:

> **Back Drive** — Home — 2:34 PM

to:

> **Back Drive (person, vehicle)** — "Person walking near parked truck on driveway" — Home — 2:34 PM

## Why Gemma 4 + Ollama

- **Already running locally** — no API costs, no cloud dependency, no rate limits
- **Gemma 4 supports vision** — multimodal input (image + text prompt) natively
- **Privacy** — camera images never leave the machine
- **Good enough** — we don't need GPT-4V accuracy; we need "person vs. deer vs. car vs. nothing"
- **Tested**: Gemma 4 31B Q8 works but at 33 GB pushes memory hard (91% pressure on 48 GB M3 Max). A smaller model (12B) is the practical target for always-on daemon use.

## Where It Fits in the Pipeline

Current flow:
```
get_new_events() → save_snapshot() → notifier.send()
```

Proposed flow:
```
get_new_events() → save_snapshot() → [analyze_snapshot()] → notifier.send()
```

The insertion point is `daemon.py:_handle_event()`, between snapshot save and notification send. The `MotionEvent.tags` field already exists but is empty for Blink — we populate it with the model's output.

### Integration Detail

```
daemon._handle_event(source, event)
  ├─ snapshot_path = await source.save_snapshot(...)
  ├─ if source.brand == "blink" and snapshot_path:
  │     tags, description = await analyzer.describe(snapshot_path)
  │     event.tags = tags            # "person, vehicle"
  │     title_suffix = f"({tags})"   # appended to camera name
  │     message_prefix = description # prepended to notification body
  └─ await notifier.send(...)
```

## New Module: `dolly/analyzer.py`

A single class, `OllamaVision`, responsible for:

1. Sending a JPEG + prompt to the local Ollama API (`POST /api/generate`)
2. Parsing the response into structured tags + a one-line description
3. Handling timeouts and failures gracefully (if Ollama is down, skip analysis and send the notification as-is)

### Prompt Design

```
Describe this security camera image in one short sentence.
Then list only the objects you see from this set: person, vehicle, animal, package, nothing.
Format: DESCRIPTION: <sentence>\nTAGS: <comma-separated>
```

Keep the prompt tight — longer prompts = longer inference. We want classification, not poetry.

### API Call

**Critical**: Gemma 4 has thinking mode enabled by default. You **must** pass `"think": false` at the top level of the request, otherwise all tokens go into internal reasoning and the response comes back empty.

Use the `/api/chat` endpoint (not `/api/generate`) — it returns structured message content.

```python
async def describe(self, image_path: Path) -> tuple[str, str]:
    """Return (tags, description). Falls back to ('', '') on failure."""
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    payload = {
        "model": self._model,
        "messages": [{
            "role": "user",
            "content": PROMPT,
            "images": [image_b64],
        }],
        "think": False,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 80},
    }
    async with self._session.post(f"{self._base_url}/api/chat", json=payload) as resp:
        result = await resp.json()
        return self._parse(result["message"]["content"])
```

Key settings:
- `think: false` — **required** for Gemma 4, disables thinking mode so tokens go to response
- `temperature: 0.2` — we want deterministic, not creative
- `num_predict: 80` — cap output tokens to keep it fast
- `stream: false` — simpler, and we need the full response anyway

## Performance — Actual Test Results (2026-04-07)

Tested on **M3 Max / 48 GB RAM** with **Gemma 4 31B Q8** (33 GB model). Memory pressure hit 91% — a smaller model is recommended for always-on use.

### Measured Times (warm model)

| Image | Content | Tags | Time |
|-------|---------|------|------|
| Back Drive.jpg (321 KB, day) | "Black car on gravel path in wooded area" | `vehicle` | 6.1s |
| House Driveway.jpg (175 KB, day) | "Person walking across yard toward log cabins" | `person` | 9.6s |
| Porch.jpg (209 KB, day) | "Person wearing hat and pink shirt in backyard" | `person` | 8.9s |
| Back Trail.jpg (326 KB, day) | "Wooded area with green foliage and sunlight" | `nothing` | 9.9s |
| N House.jpg (37 KB, night IR) | "Dark, grainy outdoor area at night" | `nothing` | 12.6s |
| Front Gate.jpg (46 KB, night IR) | "Dark, grainy wooded area at night" | `nothing` | 11.0s |

**Observations**:
- Accuracy: 100% on test set — correctly identified person, vehicle, and nothing
- Daytime: 6-10s per image
- Night/IR: 10-13s per image (slower despite smaller file sizes — more ambiguous content)
- No hallucinations — night images correctly tagged `nothing` rather than guessing
- Prompt format followed reliably every time

### Projected Performance with Smaller Model

For always-on daemon use, a **12B model** (Gemma 4 12B or similar) would:
- Use ~7-8 GB RAM instead of 33 GB
- Run in ~3-5s per image (estimated 2x faster)
- Leave headroom for the rest of the system
- Still be accurate enough for person/vehicle/animal/nothing classification

### Impact on Poll Cycle

Current poll interval: **30 seconds**

With a 12B model (estimated):

| Events per poll | Analysis time | Fits in 30s? |
|----------------|---------------|--------------|
| 1 event | 3-5s | Yes |
| 2 events | 6-10s | Yes |
| 3+ events | 9-15s | Yes |

With the 31B Q8 model:

| Events per poll | Analysis time | Fits in 30s? |
|----------------|---------------|--------------|
| 1 event | 6-13s | Yes |
| 2 events | 12-26s | Borderline |
| 3+ events | 18-39s | May overflow |

### Mitigation Options (pick one or combine)

1. **Timeout per image** — Hard cap at 15s. If Ollama hasn't responded, send the notification without tags. User still gets alerted promptly.

2. **Concurrent analysis** — Run `asyncio.gather()` on multiple images simultaneously. Ollama will serialize on a single GPU, but saves HTTP overhead.

3. **Fire-and-forget with amendment** — Send the notification immediately (no tags), then send a follow-up with the AI description.

4. **Priority queue** — Analyze only the first event immediately; queue the rest.

**Recommendation**: Start with option 1 (15-second timeout). Simple, preserves notification latency, degrades gracefully. Use a 12B model for always-on and the whole question becomes moot.

## Config Changes

```yaml
# config.yaml.example addition
ai:
  enabled: true               # Master toggle
  provider: "ollama"          # Only option for now
  ollama_url: "http://localhost:11434"
  model: "gemma4:31b-it-q8_0"  # or smaller: gemma4:12b
  timeout: 10                 # seconds, per image
  brands: ["blink"]           # Which camera brands to analyze
```

This keeps it opt-in and brand-scoped. Wyze already provides tags, so analyzing those images would be redundant cost.

## Implementation Steps

### Phase 1 — Proof of Concept (standalone script)
1. Write `tests/vision.py` — load a saved Blink snapshot, send to Ollama, print result
2. Measure actual inference time on *this* machine with *this* model
3. Tune the prompt until tags are reliable across day/night images
4. Validate that Gemma 3 27B handles low-light IR images (Blink night vision is grainy)

### Phase 2 — Module Integration
1. Create `dolly/analyzer.py` with `OllamaVision` class
2. Add `ai` config section to `dolly/config.py` and `config.yaml.example`
3. Wire into `daemon._handle_event()` with the brand gate
4. Update `notifier.send()` call to include tags/description in title/message

### Phase 3 — Hardening
1. Add timeout handling (skip analysis on timeout, log warning)
2. Add Ollama health check on startup (warn if unreachable, don't block daemon)
3. Handle model-not-found errors gracefully
4. Test with Ollama stopped/restarted mid-run

### Phase 4 — Tuning
1. Evaluate night vision / IR image accuracy
2. Consider dropping to a smaller model if 27B is too slow (Gemma 3 9B is ~3x faster)
3. Add confidence-based priority: `person` = high, `animal` = default, `nothing` = low
4. Optional: suppress `nothing` events entirely (risky — false negatives)

## Risks and Open Questions

| Risk | Severity | Mitigation |
|------|----------|------------|
| 27B model too slow on this hardware | Medium | Fall back to 9B or 4B; timeout degrades gracefully |
| Poor night vision accuracy | Medium | Test in Phase 1; IR images are low-contrast but usually have clear silhouettes |
| Ollama OOM under load | Low | 27B Q4 needs ~18 GB; if system is tight, use smaller quant or model |
| Model hallucinates objects | Low | Low temperature + constrained tag set limits damage; wrong tag > no tag |
| Blink rate limits during snapshot download | Low | Already handled — snapshot download exists today |

## What This Does NOT Do

- **No video analysis** — we extract a single frame at the 3-second mark (existing behavior). Full clip analysis would be 10x slower and unnecessary for classification.
- **No training/fine-tuning** — we use the model as-is with prompt engineering.
- **No cloud fallback** — if Ollama is down, notifications go out without AI tags. This is a feature, not a bug.
- **No Wyze analysis** — Wyze already provides object tags via their cloud. We only target the gap.

## Success Criteria

1. Blink notifications include accurate object tags >=80% of the time
2. Notification latency increases by <10 seconds on average
3. Zero missed notifications due to AI analysis failures
4. Works unattended — no manual intervention needed after setup
