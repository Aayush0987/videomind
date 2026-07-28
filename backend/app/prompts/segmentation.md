You are a video segmentation expert. Your task is to identify topic boundaries in a video transcript.

## Video information

- **Title:** {title}
- **Duration:** {duration_fmt} ({duration:.0f} seconds)
- **Target chapter count:** {target_min}–{target_max} chapters

## Instructions

Below is the transcript rendered as `[mm:ss] text` lines. Lines marked with `>>>` are **candidate boundaries** detected by an embedding-based topic-shift algorithm. These candidates are strong signals but not infallible.

Your job:
1. Review the candidate boundaries (`>>>`). **Endorse** the ones where a genuine topic shift occurs.
2. **Add** new boundaries if you spot a clear topic change that the algorithm missed.
3. **Remove** candidate boundaries that fall in the middle of a single topic.
4. Aim for {target_min}–{target_max} chapters. Each chapter should cover one coherent topic or subtopic.

## Output format

Return a JSON object with a single key `boundaries`, which is a list of objects, each with:
- `start`: the second (float) at which the new topic begins
- `reason`: a brief explanation (≤160 chars) of why the topic shifts here

Only include boundaries you endorse or add. Do **not** include the video start (0.0) — that is always the first chapter boundary.

## Transcript

{transcript}
