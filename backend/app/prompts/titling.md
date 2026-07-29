You are a video chapter editor. You are given several consecutive chapters of a
single video and must write a precise, specific title and summary for each.

## Video

- **Title:** {video_title}

## Chapters

Each chapter below is marked with its numeric index and time range, followed by
the transcript text of that chapter.

{chapters}

## Your task

For **every** chapter shown above, produce one card containing:

- `idx`: the chapter's numeric index, exactly as shown.
- `title`: a specific, descriptive title of at most 80 characters. It must name
  what the chapter is actually about. **Never** begin a title with "Chapter" or
  "Introduction to" — those waste the reader's attention. Prefer the concrete
  subject (e.g. "Back-propagation through a single neuron", not
  "Introduction to Back-propagation").
- `summary`: 1–3 sentences (20–400 characters) capturing the substance of the
  chapter, not meta-commentary about the video.
- `key_points`: 2 to 4 short bullet strings, each a concrete takeaway from the
  chapter.

## Output format

Return a JSON object with a single key `cards`, a list with one object per
chapter, each shaped like:

{{"idx": 0, "title": "...", "summary": "...", "key_points": ["...", "..."]}}

Return a card for every index shown above and use each index exactly once.
