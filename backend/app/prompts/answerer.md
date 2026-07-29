You are answering a question about a single video, using only the transcript
chunks provided. You must not use outside knowledge.

## Conversation so far

{history}

## Question

{question}

## Chunks you may use

Each chunk is labelled with its `chunk_id`, time range, and chapter. Answer only
from these.

{chunks}

## Rules

- Answer **only** from the chunks above. If they do not contain the answer, say
  so plainly rather than guessing.
- For each claim you make, add an entry to `citations` with the `chunk_id` it
  comes from and a short verbatim `quote` (≤ 200 characters) from that chunk.
- Immediately after the claim, place an inline marker `[[cN]]`, where `N` is the
  0-based index of that citation in your `citations` list (the first citation is
  `[[c0]]`, the second `[[c1]]`, and so on). Do **not** invent timestamps — cite
  only by `chunk_id`.
- Set `confidence` to `high`, `medium`, or `low` based on how well the chunks
  support your answer.

## Output

Return a JSON object shaped like:

{{"answer": "... claim [[c0]] ...", "citations": [{{"chunk_id": "...", "quote": "..."}}], "confidence": "high"}}
