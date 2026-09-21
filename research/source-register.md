# Research Source Register

**Date checked:** 2026-09-21

This register is for traceability. Architectural patterns may be learned from these sources; code reuse requires separate license review.

| Source | URL | Why reviewed | License/reuse note |
|---|---|---|---|
| Tarjoman upstream | https://github.com/Erfix404/tarjoman | baseline | MIT in repository |
| Translation Agent | https://github.com/andrewyng/translation-agent | LLM reflection workflow | README states MIT |
| OmegaT | https://github.com/omegat-org/omegat | CAT/TM/glossary/fuzzy match | GPLv3; do not copy code into MIT core |
| OmegaT AI plugin | https://github.com/Nic-J/omegat-ai-plugin | TM cache, glossary, context, local/cloud | README states MIT |
| LibreTranslate | https://github.com/LibreTranslate/LibreTranslate | self-hosted MT API | AGPLv3 |
| Argos Translate | https://github.com/argosopentech/argos-translate | offline MT library | README states MIT/CC0 dual license |
| COMET | https://github.com/Unbabel/COMET | MT evaluation | framework Apache-2.0; model licenses vary |
| DocuTranslate | https://github.com/xunbu/docutranslate | formats, async providers, MCP | verify release/license before any code reuse |
| document-translation | https://github.com/kukas/document-translation | markup extraction/reinsertion | verify before code reuse |
| llm-subtrans | https://github.com/machinewrapped/llm-subtrans | subtitle structure/context | verify before code reuse |
| subtitle-translator | https://github.com/rockbenben/subtitle-translator | timecode isolation/context/cache | verify before code reuse |
| Meetily | https://github.com/Zackriya-Solutions/meetily | local meeting ASR/summary | README states MIT |
| Vibe | https://github.com/thewh1teagle/vibe | local transcription/export | verify repository license before reuse |
| NeurAI | https://github.com/Dr-Bagheri/neurai-mvp | Persian meeting/minutes architecture | README states Apache-2.0 |
| Persian STT Pipeline | https://github.com/hosseinmirzapur/persian-stt-pipeline | Persian lecture audio → polished artifact | verify before reuse |
| Persian Meeting Assistant | https://github.com/Alaleh-Mohseni/Meeting-assistant | Persian live meeting flow | README states MIT |
| WhisperX | https://github.com/m-bain/whisperX | alignment/diarization | dependency/model terms must be checked |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | CTranslate2 ASR | verify dependency/model terms per distribution |
| Hazm | https://github.com/roshan-research/hazm | Persian NLP | verify package license before bundling |
| DadmaTools | https://github.com/Dadmatech/DadmaTools | Persian NLP/formalization/spell | verify package/model licenses |
| Parsivar | https://github.com/ICTRC/Parsivar | Persian normalization/NLP | verify package/model licenses |
| Virastar | https://github.com/aziz/virastar | Persian typography rules | verify exact license/port before reuse |
| MCP | https://github.com/modelcontextprotocol/modelcontextprotocol | agent tool protocol | use official SDK/spec |
| A2A | https://github.com/a2aproject/A2A | agent-to-agent protocol | use official SDK/spec |
| Orca transcription | https://orca-chat.ir/audio-to-text | Persian product UX research | product reference only |

| Persian TTS / Parsigo | https://github.com/nimaone/persian_tts | ONNX/G2P/voice-cloning architecture | repo currently has no detected license; do not copy code without clarification |
| Pocket-TTS Farsi v2 ONNX | https://huggingface.co/Nimaone/pocket-tts-farsi-v2-onnx | lightweight Persian clone TTS | CC-BY-NC-4.0 weights; non-commercial |
| Pocket-TTS Farsi v2 | https://huggingface.co/mehdi-hf/pocket-tts-farsi-v2 | underlying Persian TTS model | CC-BY-NC-4.0 |
| MMS Persian TTS | https://huggingface.co/facebook/mms-tts-fas | Persian fixed TTS baseline | CC-BY-NC-4.0 |
| ParsVoice XTTS | https://huggingface.co/MohammadJRanjbar/ParsVoice-XTTS | Persian XTTS/clone candidate | CPML inherited from XTTS-v2; non-commercial |
| MOSS-TTS v1.5 | https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5 | modern Persian multilingual/clone candidate | model card Apache-2.0; full lineage still review before bundling |
| OpenMOSS TTS | https://github.com/OpenMOSS/MOSS-TTS | MOSS implementation | review dependency/model lineage |
| Persian Piper weights | https://huggingface.co/SadeghK/persian-text-to-speech | lightweight Persian fixed voices | repo metadata Apache-2.0; verify each voice/data lineage |
| ManaTTS Persian | https://github.com/MahtaFetrat/ManaTTS-Persian-Tacotron2-Model | Persian TTS baseline | README states CC0 model weights; verify artifacts |
| sherpa-onnx | https://github.com/k2-fsa/sherpa-onnx | cross-platform ONNX speech runtime | Apache-2.0 code; model licenses remain separate |

| Model Context Protocol 2026-07-28 | https://blog.modelcontextprotocol.io/posts/2026-07-28/ | stateless MCP core + Tasks extension | official specification release |
| A2A 0.3 specification | https://a2a-protocol.org/v0.3.0/specification/ | optional agent-to-agent discovery/task lifecycle | official specification |
| OWASP File Upload Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html | upload/storage boundary | security guidance |
| OWASP SSRF Prevention Cheat Sheet | https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html | custom endpoint/network security | security guidance |
| SQLite Backup API | https://www.sqlite.org/backup.html | consistent live DB backup | official SQLite docs |
| SQLite WAL | https://www.sqlite.org/wal.html | same-host WAL constraints/concurrency | official SQLite docs |

## License policy

1. Do not copy code from GPL/AGPL sources into Tarjoman MIT core.
2. External model licenses are separate from library licenses.
3. Any new optional dependency gets a license/provenance entry before merge.
4. Architectural concepts, standards, and behavior learned from public systems are not a substitute for independent implementation and tests.
