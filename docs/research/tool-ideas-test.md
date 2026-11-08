# Testing the new tools on real texts (2026-11-08)

## `tarjoman book candidates` on Alice ch. 1-3 (572 words, `docs/research/real-texts/round2/book`)

The terms the project had recorded by hand (`terms.tsv`) plus the named characters in the text are the reference.

| | Result |
|---|---|
| Named entities and coined terms present in the text | Alice, White Rabbit, Rabbit, Dodo, Duchess, Caucus-race (6) |
| Found with `--min-count 2` | all 6 (recall 6/6) |
| False positives at `--min-count 2` before the fix | `I'm` (precision 6/7) |
| After the fix (contractions skipped, `Caucus-race` and the heading `Caucus-Race` merged) | no false positives; `Caucus-race` count 3 |
| Terms with count 1 (`--min-count 1`) | mixed: heading words (`Long Tale`, `Pool of Tears`), `English`, `Curiouser`. Keep the default of 3 for books; use 2 for short texts |

Limits: it only finds capitalised names and phrases. Lowercase coined terms («rabbit-hole») and catchphrases («Oh dear») are not found, so `book terms --add` stays the way to record those. One short text is a small sample; the recall figure is an anecdote, not a benchmark.

## `srt extract` / `srt merge` on the real subtitle files (`docs/research/real-texts/subs.*.srt`)

Both translated files (`subs.base.srt`, `subs.skill.srt`, 7 cues each) extract and merge cleanly against `subs.en.srt`; `srt check` on the merged skill output passes. A synthetic 2000-cue file round-trips in well under a second. The merge refuses a missing, repeated, out-of-order or empty marker, and text before the first marker (a chatbot preamble).
