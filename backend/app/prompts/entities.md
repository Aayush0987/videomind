You are an entity extractor. You are given the chapter summaries of a single
video and must list the notable entities discussed in it.

## Chapter summaries

Each line is prefixed with the second at which the chapter begins, in the form
`[123s]`, followed by the chapter title and summary.

{summaries}

## Your task

Extract at most {max_entities} distinct entities that a viewer might want more
context on. For each entity, return:

- `name`: the canonical name of the entity (at most 80 characters).
- `kind`: one of `person`, `organization`, `technology`, `concept`, `place`,
  `event`, `product`.
- `first_mention`: the second (a number, e.g. `123`) of the earliest chapter in
  which the entity appears. Read it from the `[123s]` prefix of that chapter.
- `needs_enrichment`: `true` only when a general audience would plausibly **not**
  already know what this entity is and a one-line explanation would genuinely
  help. Be conservative.

### needs_enrichment examples

- `true` — "Kullback–Leibler divergence" (a specialised concept most viewers
  could not define).
- `true` — "the Antikythera mechanism" (an obscure historical artifact).
- `false` — "Google" (a household-name organization needing no gloss).
- `false` — "the internet" (a everyday concept everyone already understands).

## Output format

Return a JSON object with a single key `entities`, a list of objects with the
fields above. Do not exceed {max_entities} entities.
