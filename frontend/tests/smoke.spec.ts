import { expect, test } from "@playwright/test";

const VIDEO_ID = "dQw4w9WgXcQ";

// Full flow against a mocked API (§18.3): paste URL → timeline advances →
// chapters render → ask a question → citation chip appears → clicking it seeks.
test("paste, process, ask, and seek from a citation", async ({ page }) => {
  // Replace the YouTube IFrame API with a fake that records seekTo calls, so we
  // can assert the citation click drives the player without a real iframe.
  await page.addInitScript(() => {
    const w = window as unknown as {
      __seeks: number[];
      YT: unknown;
      onYouTubeIframeAPIReady?: () => void;
    };
    w.__seeks = [];
    w.YT = {
      Player: class {
        constructor() {
          w.onYouTubeIframeAPIReady?.();
        }
        seekTo(seconds: number) {
          w.__seeks.push(seconds);
        }
        getCurrentTime() {
          return 0;
        }
        playVideo() {}
        destroy() {}
      },
    };
  });

  await page.route("**/api/videos", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({
        cached: false,
        video_id: VIDEO_ID,
        job_id: "job-1",
      }),
    });
  });

  // First poll: running. Second poll: ready. Proves the timeline advances.
  let jobPolls = 0;
  await page.route("**/api/jobs/job-1", async (route) => {
    jobPolls += 1;
    const ready = jobPolls > 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job_id: "job-1",
        video_id: VIDEO_ID,
        status: ready ? "ready" : "running",
        stage: ready ? "index" : "propose_boundaries",
        stage_label: ready ? "Indexing for search" : "Detecting chapter boundaries",
        progress: ready ? 1.0 : 0.4,
        retries: { segmentation: 1 },
        error_code: null,
        error_message: null,
      }),
    });
  });

  await page.route(`**/api/videos/${VIDEO_ID}`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        video_id: VIDEO_ID,
        url: `https://youtu.be/${VIDEO_ID}`,
        title: "How retrieval-augmented generation works",
        channel: "VideoMind",
        duration: 600,
        thumbnail_url: null,
        transcript_source: "captions",
        language: "en",
        chapters: [
          {
            chapter_id: `${VIDEO_ID}:ch00`,
            idx: 0,
            start: 0,
            end: 271,
            title: "The naive approach",
            summary: "Why a single prompt isn't enough.",
            key_points: ["Context windows are finite"],
          },
          {
            chapter_id: `${VIDEO_ID}:ch01`,
            idx: 1,
            start: 271,
            end: 600,
            title: "Cost of the naive approach",
            summary: "The cost scaled linearly.",
            key_points: ["Linear cost growth"],
          },
        ],
        enrichments: [],
        verification: { valid: true, repaired: true, issues: [] },
      }),
    });
  });

  await page.route(`**/api/videos/${VIDEO_ID}/ask`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        answer: "They dropped it because the cost scaled linearly [[c0]].",
        citations: [
          {
            marker: "c0",
            chunk_id: `${VIDEO_ID}:c0012`,
            start: 271,
            end: 302,
            quote: "the cost scaled linearly",
            chapter_title: "Cost of the naive approach",
          },
        ],
        confidence: "high",
        trace: {
          strategy: "decompose",
          retrieval_attempts: 2,
          chunks_retrieved: 12,
          chunks_kept: 5,
          dropped_citations: 0,
          nodes: ["plan_query", "retrieve", "grade_chunks", "answer"],
          latency_ms: 4120,
        },
      }),
    });
  });

  // Paste a URL and start analysis.
  await page.goto("/");
  await page.getByLabel("YouTube video URL").fill(`https://youtu.be/${VIDEO_ID}`);
  await page.getByRole("button", { name: "Analyze video" }).click();

  // The processing timeline shows, including the visible retry line.
  await expect(page.getByText("Analyzing")).toBeVisible();
  await expect(page.getByText(/re-segmenting/i)).toBeVisible();

  // Chapters render once the job is ready.
  await expect(
    page.getByRole("heading", { name: "Cost of the naive approach" }),
  ).toBeVisible();

  // Ask a question and get an answer with a citation chip.
  await page.getByLabel("Your question").fill("Why did they drop it?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  const citation = page.getByRole("button", { name: /Citation at 04:31/ });
  await expect(citation).toBeVisible();

  // Clicking the citation seeks the player to the citation's start time.
  await citation.click();
  await expect
    .poll(async () => page.evaluate(() => (window as unknown as { __seeks: number[] }).__seeks))
    .toContain(271);
});
