# Retrieval eval

94 on-topic and 10 off-topic golden questions.
Recall and MRR are over unique sections (chunks deduplicated by RFC section); a
subsection of a golden section counts as a hit. Chunk R@5 skips the dedup.

| mode | R@1 | R@3 | R@5 | MRR | chunk R@5 |
|---|---|---|---|---|---|
| vector | 0.39 | 0.64 | 0.77 | 0.541 | 0.74 |
| keyword | 0.20 | 0.40 | 0.54 | 0.334 | 0.51 |
| hybrid | 0.37 | 0.67 | 0.73 | 0.534 | 0.72 |

## On-topic threshold (top vector cosine similarity)

| threshold | false refusal (on-topic refused) | false answer (off-topic answered) |
|---|---|---|
| 0.60 | 0.00 | 0.60 |
| 0.61 | 0.00 | 0.60 |
| 0.62 | 0.00 | 0.60 |
| 0.63 | 0.00 | 0.60 |
| 0.64 | 0.00 | 0.60 |
| 0.65 | 0.00 | 0.60 |
| 0.66 | 0.00 | 0.40 |
| 0.67 | 0.00 | 0.40 |
| 0.68 | 0.00 | 0.40 |
| 0.69 | 0.00 | 0.30 |
| 0.70 | 0.00 | 0.30 |
| 0.71 | 0.00 | 0.30 |
| 0.72 | 0.00 | 0.20 |
| 0.73 | 0.02 | 0.10 |
| 0.74 | 0.03 | 0.10 |
| 0.75 | 0.06 | 0.00 |
| 0.76 | 0.13 | 0.00 |
| 0.77 | 0.16 | 0.00 |
| 0.78 | 0.26 | 0.00 |
| 0.79 | 0.36 | 0.00 |
| 0.80 | 0.51 | 0.00 |
| 0.81 | 0.60 | 0.00 |
| 0.82 | 0.67 | 0.00 |
| 0.83 | 0.76 | 0.00 |
| 0.84 | 0.81 | 0.00 |
| 0.85 | 0.93 | 0.00 |

Configured `ON_TOPIC_THRESHOLD` = 0.74: the highest threshold whose
false-refusal rate is at most 5%, with the false-answer rate as the tie-break.

Golden set sha256: `66ce9f22c5ee49db33e4946e1e680f59cfcecda0892dd5d9a8920e48abcc8faa`
Commit: `ae5b1e9`
