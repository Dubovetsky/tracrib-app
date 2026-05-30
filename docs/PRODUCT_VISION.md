# Product Vision

## Product

Transcrib App

## Mission

Provide fast, accurate and reliable transcription of audio recordings into readable text.

The product should be useful for:

* meetings;
* interviews;
* podcasts;
* consultations;
* business conversations;
* product discussions;
* software engineering discussions.

---

## Primary User Value

A user uploads audio and receives a transcript that:

* accurately reflects spoken content;
* preserves meaning;
* is easy to read;
* requires minimal manual correction.

---

## MVP Goals

The MVP must support:

### Audio Upload

* local audio files;
* common formats;
* long recordings.

### Speech Recognition

* Russian language;
* speaker separation;
* high transcription accuracy.

### Transcript Review

* readable transcript;
* timestamps;
* speaker labels.

### Transcript Export

* TXT;
* Markdown;
* DOCX.

---

## Non-Goals For MVP

Do not prioritize:

* team collaboration;
* enterprise administration;
* complex permissions;
* workflow automation;
* CRM integrations;
* analytics dashboards.

---

## Product Quality Priorities

Order of importance:

1. Accuracy
2. Reliability
3. Usability
4. Performance
5. Scalability

---

## Transcription Principles

The transcript should remain faithful to the original speech.

The system should:

* preserve meaning;
* preserve speaker structure;
* preserve chronology.

The system should not:

* summarize;
* rewrite;
* invent information;
* infer facts not present in audio.

---

## ASR Strategy

Keep transcription prompts minimal.

Use short domain hints.

Use hotwords separately.

Avoid prompt designs that increase hallucinations.

---

## Transcript Improvement Strategy

Post-processing exists only to improve readability.

Allowed:

* spelling fixes;
* punctuation fixes;
* capitalization fixes;
* terminology normalization.

Forbidden:

* content generation;
* summarization;
* paraphrasing;
* information expansion.

---

## Speaker Strategy

Speaker identities must never be guessed.

Names may only appear when explicitly confirmed in transcript content.

---

## Long-Term Vision

Future versions may include:

* multi-language transcription;
* local inference;
* cloud inference;
* real-time transcription;
* translation;
* transcript search;
* AI-assisted transcript analysis.

These features must not compromise transcription accuracy.
