# Audio, Meeting, and Lecture Notes Research

## Owner request

Find and learn from systems where a meeting/class audio file becomes useful Persian notes/minutes.

The exact remembered project is not identifiable with certainty from description alone. The following candidates closely match the request.

## 1. NeurAI — Persian-first meeting assistant

Source: https://github.com/Dr-Bagheri/neurai-mvp

Key ideas:
- Persian-first offline/on-prem architecture,
- faster-whisper transcription,
- speaker labels,
- summaries/decisions/action items,
- formal Iranian meeting minutes,
- spoken→written register conversion,
- Word/PDF export,
- skills/tool layer,
- local/cloud model routing.

Tarjoman lesson:
the valuable feature is not “Whisper support”; it is the **artifact chain**:
raw audio → evidence-preserving transcript → cleaned/formal Persian → structured knowledge outputs.

## 2. Persian STT Pipeline — lecture audio to publishable Persian

Source: https://github.com/hosseinmirzapur/persian-stt-pipeline

Key ideas:
- faster-whisper large-v3,
- VAD,
- Persian ASR cleanup,
- skill-driven polishing,
- lecture audio → structured print-ready artifact,
- provenance.

This is a particularly close match for “give it class/session audio and get useful Persian notes/article”.

## 3. Persian Meeting Assistant

Source: https://github.com/Alaleh-Mohseni/Meeting-assistant

Key ideas:
- live Persian transcription,
- participant/speaker handling,
- question detection,
- GPT summary,
- browser/extension mode.

Tarjoman lesson:
question extraction and participant metadata can enrich meeting/lecture outputs, but browser DOM coupling should stay outside core.

## 4. Meetily

Source: https://github.com/Zackriya-Solutions/meetily

Key ideas:
- local-first meeting recording/transcription,
- Whisper/Parakeet,
- provider-flexible summaries,
- custom OpenAI-compatible endpoint,
- desktop packaging,
- privacy emphasis.

Tarjoman lesson:
provider flexibility + local ASR is a proven product pattern.

## 5. Vibe

Source: https://github.com/thewh1teagle/vibe

Key ideas:
- offline audio/video transcription,
- multiple export formats,
- batch operation,
- summarization integration.

Tarjoman lesson:
transcription should accept files directly and produce portable artifacts even without a meeting UI.

## 6. WhisperX / faster-whisper

Sources:
- https://github.com/m-bain/whisperX
- https://github.com/SYSTRAN/faster-whisper

Patterns:
- faster Whisper inference via CTranslate2,
- timestamps/alignment,
- optional speaker diarization in WhisperX.

Tarjoman decision:
ASR is an adapter. Diarization is optional. Core translation must not import the ASR stack.

## 7. Persian commercial pattern: Orca transcription

Source: https://orca-chat.ir/audio-to-text

Observed product flow:
audio/video → readable Persian transcript → continue to chat for summary, notes, or meeting output.

Tarjoman lesson:
users understand one upload followed by reusable derivative artifacts. We should model these derivatives explicitly rather than hide everything in one “summary” response.

## Recommended Tarjoman audio modes

### Lecture mode
- transcript,
- cleaned transcript,
- structured notes,
- concepts/definitions,
- examples,
- questions,
- timestamp references.

### Meeting mode
- transcript + speakers,
- topics,
- decisions,
- action items,
- open questions,
- formal minutes,
- evidence segment references.

### Subtitle mode
- timestamp-preserving SRT/VTT,
- optional bilingual cues,
- translation context across neighboring cues.

## Non-negotiable safety/reliability rules

- raw transcript is immutable evidence,
- derived cleanup/formalization is separately versioned,
- summaries cite segment IDs,
- action-item owner/due date is not invented,
- audio module is optional dependency,
- local-only policy blocks cloud transcription/summarization,
- long audio jobs checkpoint/resume.
