# Coding Principles

## Product First

Every engineering decision must improve at least one of:

* transcription accuracy;
* reliability;
* maintainability;
* usability;
* performance.

Avoid complexity without measurable value.

---

## MVP First

Prefer the simplest solution that solves the problem.

Avoid:

* premature optimization;
* speculative architecture;
* unnecessary abstractions.

---

## Evidence-Based Decisions

Do not preserve existing code merely because it already exists.

Before implementing:

1. Understand the current behavior.
2. Identify the problem.
3. Identify the root cause.
4. Evaluate alternatives.
5. Select the simplest effective solution.

---

## Simplicity Over Cleverness

Prefer code that is:

* readable;
* explicit;
* testable;
* maintainable.

Avoid:

* hidden side effects;
* magic values;
* excessive indirection;
* over-engineering.

---

## Transcription Quality

Transcription quality is the primary business metric.

Prioritize:

* accuracy;
* robustness;
* consistency;
* predictability.

Never sacrifice transcript quality for architectural purity.

---

## ASR Principles

Keep ASR prompts short.

Example:

Русская рабочая встреча. Возможны IT и product management термины. Сохраняй речь дословно.

Use short hotword lists.

Avoid:

* prompt echo;
* hallucinations;
* large glossary injection;
* generated context.

---

## Transcript Post-Processing

Transcript polishing must be conservative.

Allowed:

* punctuation fixes;
* spelling fixes;
* capitalization fixes;
* normalization of obvious technical terms.

Forbidden:

* summarization;
* paraphrasing;
* rewriting;
* adding information;
* removing information;
* changing meaning.

When uncertain, keep the original transcript.

---

## Speaker Rules

Never infer speaker identities.

Never rename speakers from weak context.

Rename speakers only after explicit self-identification in the transcript.

If uncertain, preserve existing speaker labels.

---

## Reliability First

Failures should be:

* visible;
* understandable;
* recoverable.

Avoid silent failures.

Prefer warnings over hidden behavior.

---

## Testing

Every non-trivial change should include tests.

Critical areas:

* transcription pipeline;
* transcript polish pipeline;
* speaker handling;
* JSON parsing;
* prompt processing;
* safety validation.

Bug fixes should include regression tests.

---

## Security

Treat all user input as untrusted.

Validate inputs.

Fail safely.

Avoid exposing sensitive information through logs or prompts.

---

## Documentation

Significant architectural changes should be documented.

Documentation should explain:

* why;
* what changed;
* trade-offs;
* risks.
