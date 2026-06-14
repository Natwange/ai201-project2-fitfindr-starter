# FitFindr 🛍️

FitFindr is a tool-using agent that helps a shopper find a secondhand clothing item, style it against their existing wardrobe, and turn the look into a shareable caption. The user types a natural-language request (e.g. *"vintage graphic tee under $30, size M"*) and the agent runs a three-step planning loop: **search → suggest outfit → create fit card**.

## Project Layout

```
ai201-project2-fitfindr-starter/
├── data/
│   ├── listings.json          # 40 mock secondhand listings
│   └── wardrobe_schema.json   # Wardrobe format + example/empty wardrobes
├── utils/
│   └── data_loader.py         # load_listings(), get_example_wardrobe(), get_empty_wardrobe()
├── tests/
│   └── test_tools.py          # pytest tests, one per failure mode
├── tools.py                   # The three tools: search_listings, suggest_outfit, create_fit_card
├── agent.py                   # Planning loop (run_agent) + query parsing + session state
├── app.py                     # Gradio UI (handle_query)
├── conftest.py                # Puts the project root on sys.path for pytest
├── planning.md                # Design spec (tools, planning loop, diagram, walkthrough)
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file in the project root (free key at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

`suggest_outfit` and `create_fit_card` call the Groq API (model `llama-3.3-70b-versatile`, set in [tools.py](tools.py)). `search_listings` runs fully offline against the local dataset.

## Running

```bash
python app.py        # launch the Gradio web UI (http://localhost:7860)
python agent.py      # run the two built-in CLI test cases (happy path + no-results)
pytest tests/        # run the test suite
```

---

## Tool Inventory

The agent uses three tools, defined in [tools.py](tools.py).

### 1. `search_listings(description, size, max_price) -> list[dict]`

**Purpose:** Search the mock secondhand dataset for items matching the user's request. Runs offline using `load_listings()` from the data loader.

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item, e.g. `"vintage graphic tee"`. |
| `size` | `str \| None` | Size to filter by (case-insensitive substring, so `"M"` matches `"S/M"`). `None` skips size filtering. |
| `max_price` | `float \| None` | Inclusive price ceiling. `None` skips price filtering. |

**Output:** A `list[dict]` of up to the **top 3** matching listings, sorted by relevance (keyword-overlap score, highest first). Each listing has: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`. Returns an empty list `[]` when nothing matches — never raises.

### 2. `suggest_outfit(new_item, wardrobe) -> str`

**Purpose:** Given a found item and the user's wardrobe, generate 1–2 complete outfit ideas that pair the new piece with items the user already owns (by name), using the LLM.

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict returned by `search_listings` (the item the user is considering). |
| `wardrobe` | `dict` | A wardrobe dict in `wardrobe_schema.json` format — has an `"items"` key listing pieces with `name`, `category`, `colors`, `style_tags`, `notes`. |

**Output:** A non-empty `str` of styling advice. With a populated wardrobe it names specific pieces; with an empty wardrobe it returns general styling advice for the item alone.

### 3. `create_fit_card(outfit, new_item) -> str`

**Purpose:** Turn an approved outfit into a short, casual, social-media-ready caption.

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The styling suggestion string from `suggest_outfit`. |
| `new_item` | `dict` | The listing dict, used to reference item title, price, and platform in the caption. |

**Output:** A `str` caption (2–4 sentences) mentioning the item, price, and platform naturally. Uses a higher LLM temperature so captions vary across runs. If `outfit` is empty/whitespace, returns a descriptive error-message string instead of raising.

---

## Planning Loop

Implemented as `run_agent(query, wardrobe)` in [agent.py](agent.py). The loop is linear with one early-exit branch:

1. **Initialize** a fresh `session` dict.
2. **Parse the query** (`_parse_query`) into `description`, `size`, and `max_price` using regex. (Regex was chosen over an LLM call for speed and determinism.)
3. **Call `search_listings`** with the parsed parameters and store the result in `session["search_results"]`.
4. **Branch on the result:** if the list is **empty**, store a helpful message in `session["error"]` and **return immediately** — `suggest_outfit` is never called with empty input.
5. Otherwise, store the top result as `session["selected_item"]`.
6. **Call `suggest_outfit`** with the selected item + wardrobe; store the string in `session["outfit_suggestion"]`.
7. **Call `create_fit_card`** with that suggestion + the selected item; store the result in `session["fit_card"]`.
8. **Return** the session. Success is indicated by `session["error"]` being `None`.

The loop ends when either an error is set (early exit) or a fit card is produced. The two LLM calls are wrapped in `try/except` so an API failure sets `session["error"]` rather than crashing.

---

## State Management

All information for a single interaction lives in one **session dict** (`_new_session`), which is the single source of truth. Each tool's output is written back to the session and read by the next step — nothing is re-derived or re-prompted between tools.

| Key | Set by | Used by |
|-----|--------|---------|
| `query` | initial input | — |
| `parsed` | `_parse_query` | `search_listings` |
| `search_results` | `search_listings` | item selection |
| `selected_item` | item selection | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | initial input | `suggest_outfit` |
| `outfit_suggestion` | `suggest_outfit` | `create_fit_card` |
| `fit_card` | `create_fit_card` | final output |
| `error` | any failing step | UI / caller |

State flow was verified by identity: the exact `selected_item` dict object passed into `suggest_outfit` and `create_fit_card` is the same object stored in the session (`is` comparison returns `True`), and the `outfit_suggestion` string returned by `suggest_outfit` is the same object handed to `create_fit_card`.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|--------------|----------------|
| `search_listings` | No listing matches the query | Returns `[]`; the loop sets `session["error"]` with advice (broaden description, drop the size filter, raise `max_price`) and stops without calling `suggest_outfit`. |
| `suggest_outfit` | Wardrobe is empty / LLM call fails | Empty wardrobe → returns general styling advice (graceful, non-empty string). An API exception is caught and stored in `session["error"]`. |
| `create_fit_card` | Outfit input missing or incomplete | Empty/whitespace `outfit` → returns a descriptive message before any LLM call; the loop also guards against an empty return value. |

**Concrete example from testing — the no-results branch:**

Running `python agent.py` with the second built-in case, query `"designer ballgown size XXS under $5"`:

- `_parse_query` → `{"description": "designer ballgown", "size": "XXS", "max_price": 5.0}`
- `search_listings` → `[]` (no match)
- `session["error"]` → *"No listings matched your search. Try broadening the description, removing the size filter, or raising your maximum price."*
- `session["fit_card"]` → `None`
- `suggest_outfit` was **never called** (verified with a spy wrapper).

**Concrete example — the `create_fit_card` guard:**

```python
>>> create_fit_card("", {"title": "Y2K Baby Tee", "price": 18.0})
"Can't create a fit card yet — no outfit suggestion was provided."
```

It returns a message string instead of raising, and never reaches the LLM call. This is covered by `test_create_fit_card_empty_outfit` in [tests/test_tools.py](tests/test_tools.py).

---

## Spec Reflection

A few things changed between the planning.md spec and the working implementation:

- **`suggest_outfit` returns a string, not `list[dict]`.** planning.md originally described returning up to three structured outfit dicts. The implementation returns a single styling-advice **string**, matching the tool stub's signature (`-> str`) and what `create_fit_card` consumes. This is simpler and avoids inventing a structured outfit schema the rest of the pipeline didn't need.
- **Empty wardrobe is handled gracefully, not by blocking.** planning.md's error table said to *stop and ask the user* for wardrobe pieces. In practice `suggest_outfit` instead returns useful general styling advice for the item on its own, so the interaction still completes. This is friendlier and avoids a dead-end.
- **Session key is `outfit_suggestion` (singular).** planning.md's State Management section uses `outfit_suggestions` / `selected_outfit` (plural). Because `suggest_outfit` returns one string rather than a list, the code uses the single `outfit_suggestion` key defined in the `agent.py` session stub.
- **Query parsing was added.** The tool specs assumed parameters were already extracted; the real entry point takes a raw sentence, so `_parse_query` (regex) was added to turn `"vintage graphic tee under $30, size M"` into `description` / `size` / `max_price`. Testing surfaced two bugs that were fixed: multi-token sizes like `"W30 L30"` weren't captured, and digits inside a size token (`"W30"`) were being misread as a price — the price regex now requires a `$` or a keyword.
- **No automatic retry loop.** planning.md mentioned retrying the search 2–3 times. The implementation does a single search and stops on empty results; the user re-queries through the UI instead. The early-termination guarantee (never call `suggest_outfit` on empty input) is preserved.

---

## AI Usage

This project was built with **Claude (Claude Code)** as the coding assistant. Two specific instances:

### 1. Implementing the three tools

- **Input given:** The **Tools** section of planning.md (each tool's parameter names, types, return value, and failure mode), the **Error Handling** table, and a pointer to `utils/data_loader.py` plus the field lists in `listings.json` and `wardrobe_schema.json` so the code filtered against real fields.
- **What it produced:** `search_listings` (keyword-overlap scoring over the dataset, top-3, empty list on no match), and the two LLM-backed tools `suggest_outfit` / `create_fit_card` using the shared Groq client.
- **What I changed / overrode:** Pinned the model to `llama-3.3-70b-versatile` in one constant since none was specified. Kept `search_listings` capped at the **top 3** results to match the planning.md spec. Confirmed `create_fit_card`'s empty-outfit guard runs *before* the LLM call (deterministic, no API cost) and verified it returns a message rather than raising.

### 2. Implementing the planning loop

- **Input given:** The **Architecture** Mermaid diagram (showing call order and the error branch), the **Planning Loop** section, and the **State Management** section (the session keys), plus the three tool signatures.
- **What it produced:** `run_agent()` wiring the tools together through the session dict, with the early-exit branch when `search_listings` returns empty, and a regex `_parse_query` helper to turn the raw query into tool parameters.
- **What I changed / overrode:** Reviewed the generated loop against the spec checklist before trusting it — confirmed it branches on the `search_listings` result, writes every value into the session dict, and does **not** call all three tools unconditionally. Caught and fixed two `_parse_query` regex bugs (multi-token sizes; size digits misread as price). Chose the singular `outfit_suggestion` session key to match the `agent.py` stub and the string return type, overriding the plural naming in the planning doc. Added `try/except` around the LLM calls so API failures populate `session["error"]` instead of crashing.