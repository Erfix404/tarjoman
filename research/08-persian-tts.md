# Persian TTS Research — production integration

**Research date:** 2026-09-21  
**Primary target reviewed:** https://github.com/nimaone/persian_tts  
**Observed HEAD:** `e834bd65ac622f376c4d2050821decf5eb95241c`

## 1. Executive conclusion

`nimaone/persian_tts` is one of the most useful recent Persian TTS engineering references for Tarjoman because it demonstrates a practical CPU-only ONNX conversion of Pocket-TTS Farsi v2 with:
- Persian G2P,
- short-reference voice cloning,
- long-text phrase/chunk planning,
- bounded parallel generation,
- reference-state caching,
- seed reproducibility,
- retry/quality heuristics,
- manual phoneme correction,
- FastAPI demo.

However, it is **not suitable as Tarjoman's commercial production default**:
1. Pocket-TTS Farsi v2 weights are CC-BY-NC-4.0.
2. The GitHub repository currently has no recognized repository license file/metadata, so source-code reuse rights are not explicit.
3. The included server is explicitly a local demo, not a hardened service.
4. Project age/activity are very recent; behavior is still being corrected through issues/PRs.

Decision: independently implement the architectural patterns behind a TTS port; keep this specific engine/model behind research/non-commercial policy unless licensing changes.

## 2. Technical architecture observed

### ONNX runtime path
The project exports the TTS/G2P stack into an ONNX package and runs without PyTorch at inference time.

Reported package elements include:
- unified FlowLM step,
- Mimi encoder,
- Mimi decoder state step,
- G2P encoder/decoder,
- host constants/state files,
- manifest.

This is an excellent packaging pattern: model package contains an explicit manifest and runtime assets rather than relying on opaque global files.

### G2P
Pocket Farsi v2 expects romanized phonemes, not raw Persian script. The project runs a Persian G2P first and exposes phonemization separately.

Architectural lesson: G2P is a contract of its own, not hidden inside one engine.

### Long-text planning
Observed techniques:
- sentence splitting,
- punctuation-aware phrases,
- chunk token budget,
- boundary repair for Persian function words/Ezafe-like relationships,
- phrase packing,
- explicit pause durations.

Architectural lesson: long-form speech planning belongs outside the neural engine.

### Voice reference
- short reference audio,
- resample/mono,
- hot-onset trimming,
- cached encoded reference state,
- cache size bounded.

Architectural lesson: reference preprocessing/cache is engine adapter infrastructure with explicit lifecycle.

### Stochastic reliability
The project uses seed handling and retries after acoustic heuristics such as silence/duration/dead-air anomalies.

Architectural lesson: stochastic synthesis requires independent output validation and bounded retry.

### Parallelism
Independent chunks can generate in a bounded thread pool. Internal ONNX threads are deliberately limited to avoid oversubscription.

Architectural lesson: concurrency budgets must consider engine-level threads and outer job concurrency together.

## 3. Production gaps observed

### License
GitHub repository metadata currently reports no repository license. The model package itself clearly states Pocket Farsi v2 is CC-BY-NC-4.0.

Action for Tarjoman:
- do not copy repository code,
- do not bundle model weights in commercial release,
- store model/code licenses separately in ModelManifest.

### Demo server
The server warns that non-loopback exposure is unauthenticated. It accepts disk-writing voice uploads.

Production differences required:
- auth,
- request/upload byte caps,
- quota,
- temp storage,
- user/project scoping,
- artifact IDs,
- persistent jobs,
- cleanup/retention,
- rate limiting.

### Upload handling
The demo reads the entire uploaded file before decode; there is no production ingress byte limit in the observed code path.

Tarjoman must enforce limits before/until stream exhaustion.

### Concurrency
A global engine lock serializes generation endpoints. This is safe for the demo but not a final multi-user scheduler.

Tarjoman uses persistent jobs + per-device/engine semaphore.

### Output persistence
Demo-generated audio lives in an in-memory store; uploads go to a local folder.

Tarjoman outputs go through the content-addressed artifact store.

### Quality evidence
Waveform similarity to the original PyTorch implementation proves ONNX conversion fidelity, not Persian end-user quality.

Tarjoman TTS needs independent pronunciation/intelligibility/listening/long-form metrics.

## 4. Valuable issue/PR evidence

### Pronunciation correction
A reported case converted English `test` into a wrong phoneme sequence. The project added manual phoneme editing.

Tarjoman design:
manual correction becomes an approved pronunciation lexicon entry with provenance and reuse.

### Reference-voice instability
An open issue reports one bundled reference voice producing bad/irrelevant output while others work.

Tarjoman design:
voice references/voice profiles themselves need a quality/status lifecycle; “model passed” is not enough.

### Dependency drift
A fresh-install issue exposed a missing runtime dependency and was corrected.

Tarjoman design:
clean-env install smoke tests for every extra/profile.

## 5. Model/license landscape

### Pocket-TTS Farsi v2
- ~109.5M parameters,
- CPU-oriented,
- voice cloning from short reference,
- strong engineering fit,
- CC-BY-NC-4.0 model license.

Use: research/non-commercial adapter only unless separately licensed.

### Meta MMS Persian
A Persian TTS checkpoint exists, but its model license is also CC-BY-NC-4.0.

Use: research benchmark, not commercial default.

### XTTS-derived Persian models
Persian fine-tunes exist, but XTTS-v2 base uses Coqui Public Model License restricting commercial use.

Use: non-commercial unless legal status/permission changes.

### MOSS-TTS v1.5
Current model card lists Persian and Apache-2.0. It supports long-form, multilingual synthesis, voice cloning and pronunciation/pause controls.

Tradeoff:
the published model is very large (~8.5B parameters; BF16 weight set is many GB), so it belongs to a heavy server/GPU profile rather than base/local-laptop Tarjoman.

Use: high-quality commercial-eligible candidate subject to full lineage/security/performance review.

### Persian Piper/ONNX voices
Current ecosystem includes Persian fixed voices and ONNX deployment patterns. Some published Persian weight collections identify Apache-2.0.

Use: strong lightweight fixed-voice candidate, but **verify each individual voice/model/data license** before production or redistribution.

### ManaTTS/Tacotron-derived Persian models
Some published weights state CC0.

Use: commercial-compatible baseline candidate if quality/runtime meet the product gate.

### Aava/Orpheus Persian
Recent Persian model cards may state Apache-2.0, but model ancestry/base terms must be verified end-to-end before approval.

Use: candidate only with license status initially `unknown`.

## 6. Candidate matrix

| Candidate | Persian | Clone | Lightweight | Reported license | Production status |
|---|---:|---:|---:|---|---|
| Pocket Farsi v2 ONNX | yes | yes | excellent CPU | CC-BY-NC-4.0 | research only |
| MMS Persian | yes | no/limited | moderate | CC-BY-NC-4.0 | research only |
| ParsVoice/XTTS | yes | yes | heavy | CPML lineage | non-commercial |
| Persian Piper voices | yes | fixed/multi voice | excellent | per-voice; some Apache-labeled | bake-off + license audit |
| ManaTTS family | yes | varies | older/heavier stack | some CC0 weights | bake-off |
| MOSS-TTS v1.5 | yes | yes | no; very large | Apache-2.0 model card | heavy server candidate |
| future models | maybe | maybe | varies | unknown | blocked until manifest |

## 7. Tarjoman decisions derived from this research

1. TTS is an optional port-driven subsystem.
2. Speech planning is engine-independent.
3. Pronunciation lexicon/G2P is first-class.
4. License gating happens before model loading/downloading.
5. Fixed-voice and voice-clone engines share one contract but different policy.
6. Voice references have validation, status, retention, and provenance.
7. Acoustic quality gate is separate from synthesis.
8. TTS evaluation is independent.
9. Pocket ONNX can be a research compatibility adapter without bundling.
10. Tarjoman does not promise one permanent default model; defaults are selected from an evidence-backed model registry.

## 8. Sources

- https://github.com/nimaone/persian_tts
- https://huggingface.co/Nimaone/pocket-tts-farsi-v2-onnx
- https://huggingface.co/mehdi-hf/pocket-tts-farsi-v2
- https://github.com/mallahyari/pocket-tts
- https://huggingface.co/facebook/mms-tts-fas
- https://huggingface.co/coqui/XTTS-v2
- https://huggingface.co/MohammadJRanjbar/ParsVoice-XTTS
- https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5
- https://github.com/OpenMOSS/MOSS-TTS
- https://huggingface.co/SadeghK/persian-text-to-speech
- https://github.com/MahtaFetrat/ManaTTS-Persian-Tacotron2-Model
- https://github.com/k2-fsa/sherpa-onnx
