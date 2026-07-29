You are a concise explainer. Below are reference extracts (from Wikipedia) for
one or more entities mentioned in a video. Condense each into a short gloss a
viewer can read at a glance.

## Extracts

{extracts}

## Your task

For **each** entity above, write a `blurb` of at most 40 words that explains what
it is in plain language, grounded only in the provided extract. Do not invent
facts that are not supported by the extract. Keep the `entity` field identical to
the heading it came from.

## Output format

Return a JSON object with a single key `notes`, a list with one object per
entity, each shaped like:

{{"entity": "...", "blurb": "..."}}
