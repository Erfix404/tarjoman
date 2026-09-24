---
name: tarjoman-hermes
description: Hermes Agent runtime skillpack (v2) for Tarjoman universal Persian translation, Najafi/Samii anti-calque editing, Typst PDF/EPUB3 typesetting, and resumable book projects with manifest cache, character bible, and termbase.
---

# Tarjoman Super-Skill v2 for Hermes Agent Runtime (پکیج تخصصی هرمس برای ترجمان)

This skillpack integrates the **Tarjoman Universal Persian Translation Engine v2** with the **Hermes Agent** runtime (including Hermes 2 Pro, Hermes 3, and OpenHermes agentic reasoning loops). It enables autonomous multi-turn translation workflows, automated CLI tool invocation, Najafi/Samii anti-calque editing, Typst PDF + EPUB3 typesetting, and resumable book projects with manifest cache, character bible, and domain termbase.

> Actual CLI signatures: `translate` takes a positional `INPUT_FILE` (use `-o` for output, `-d` for domain, `--composer` for format). There are no `--input`/`--local`/`--model`/`--provider` flags. Composers: `bilingual`, `html`, `typst`, `epub`.

---

## 1. Hermes System Prompt & Agent Persona

When initializing a Hermes Agent for Persian translation tasks, load the following core system prompt:

```xml
<system_prompt>
You are Hermes-Tarjoman, an elite literary and technical Persian translation agent powered by the Hermes Agentic Framework and Tarjoman engine.

CORE DIRECTIVES:
1. Purity & Style: Enforce the Hermes Zero Em-Dash protocol. Never output em-dashes ('—') or en-dashes ('–') in narrative or literary Persian. Replace with commas, appositives, conjunctions, or rhythmic sentence splitting.
2. Anti-Calque Doctrine: Eradicate mechanical English calques ('توسط' in passives, 'نقش بازی کردن', 'روی کسی حساب کردن', 'در پایان روز'). Reconstruct sentences using active, authentic Persian syntax.
3. Quotation Integrity: Exclusively use Persian angle quotation marks «...».
4. Typography & ZWNJ: Strictly apply Zero-Width Non-Joiner (U+200C) for prefixes ('می‌'), suffixes ('ها'), and compounds.
5. Five-Pass Reflection: Always execute pre-analysis, draft, self-critique, typographic polish, and MQM audit before finalizing output.
</system_prompt>
```

---

## 2. Autonomous Tool Invocation via Hermes Function Calling

Hermes Agents can directly invoke Tarjoman CLI tools or Python libraries via structured tool calls:

### Available Tool Declarations for Hermes

```json
[
  {
    "type": "function",
    "function": {
      "name": "tarjoman_route",
      "description": "Classify input text into one of 10 specialized translation domains.",
      "parameters": {
        "type": "object",
        "properties": {
          "text": {"type": "string", "description": "Source English text to analyze"}
        },
        "required": ["text"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "tarjoman_translate",
      "description": "Execute 5-pass reflection translation on text or file.",
      "parameters": {
        "type": "object",
        "properties": {
          "text": {"type": "string", "description": "Source text to translate"},
          "domain": {
            "type": "string",
            "enum": ["literary", "scientific", "philosophy", "legal", "technical", "medical", "media", "financial", "classical", "transcreation"],
            "description": "Optional domain override"
          },
          "composer": {
            "type": "string",
            "enum": ["bilingual", "html", "typst", "epub"],
            "description": "Publishing composer format"
          }
        },
        "required": ["text"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "tarjoman_lint",
      "description": "Lint Persian markdown text for em-dashes, calques, quote balance, and Arabic characters.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_path": {"type": "string", "description": "Absolute path to Persian markdown file"}
        },
        "required": ["file_path"]
      }
    }
  }
]
```

---

## 3. Local vs. Remote Inference Routing

Hermes Agent workflows support dual-tier execution. Route Tier A/B through your own Hermes runtime configuration; the Tarjoman CLI itself has no `--local`/`--model`/`--provider` flags — it runs the deterministic 5-pass pipeline locally:

### Tier A: Local Autonomous Inference (Offline / Private)
- **Engines**: Ollama, vLLM, llama.cpp, or ExLlamaV2.
- **Recommended Models**: `Hermes-3-Llama-3.1-8B`, `Hermes-3-Llama-3.1-70B`, `Qwen-2.5-Coder-32B`.
- **Use Cases**: Confidential legal contracts, proprietary software codebases, patient medical data, and offline batch translation.
- **CLI Command** (Tarjoman side — deterministic pipeline, no model flags):
  ```bash
  tarjoman translate document.txt -o document.fa.md
  ```

### Tier B: Remote High-Capacity Cloud Inference
- **Providers**: Together AI, OpenRouter, Anthropic Claude 3.5/3.7, OpenAI GPT-4o.
- **Use Cases**: Long-form classic literature, high-complexity philosophical treatises, large-scale book localization.
- **CLI Command** (Tarjoman side — translate first, then typeset):
  ```bash
  tarjoman translate book.txt -d literary -o book.fa.md
  tarjoman compose epub book.fa.md -o book.epub --title "My Book"
  ```

---

## 4. Multi-Turn Human-Emulation Loop for Hermes

In multi-step autonomous sessions, Hermes proceeds as follows:

```
Step 1: Receive User Input Document
Step 2: Execute `tarjoman_route(text)` -> Obtain domain profile & heuristics
Step 3: Call Stage 1 Pre-Analysis -> Mask formulas, code fences, and tokens
Step 4: Generate Draft Segment by Segment (consulting StateManager termbase)
Step 5: Execute Self-Critique (Accuracy, Fluency, Terminology, Style)
Step 6: Apply AntiCalqueEngine and TypographicRefiner
Step 7: Run AuditStage & Linter -> If quality < 85%, iterate polish
Step 8: Call selected composer (Typst/EPUB3/HTML/Bilingual) -> Produce deliverable
```

---

## 5. Resumable Book Projects (v2)

Long-form Hermes translations run as resumable book projects with three memory modules:

```bash
tarjoman book init "My Book" -o ./my-book   # scaffold manifest.json + terms.tsv
tarjoman book manifest ./my-book            # SHA-256 chunk cache: resume, skip translated
tarjoman book characters ./my-book --add "Harry:هری:brave:شما" --list
tarjoman book terms ./my-book --add "wand=چوب‌دستی:literary" --search wand --cascades
```

- **Manifest** (`tarjoman.memory.BookManifestManager`): SHA-256 chunk/chapter caching; `pending_chunks()` tells the agent what still needs translation.
- **Character Bible** (`tarjoman.memory.CharacterBible`): voice, transliteration, gender, tone, تو/شما address pronoun per character — query before drafting dialogue.
- **Termbase** (`tarjoman.memory.Termbase`, SQLite): domain-tagged EN→FA terms with cascade re-translation events; acknowledge cascades after re-translating affected segments.
