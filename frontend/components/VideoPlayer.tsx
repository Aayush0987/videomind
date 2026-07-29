"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

// Minimal shape of the bits of the IFrame API we touch.
interface YTPlayer {
  seekTo: (seconds: number, allowSeekAhead: boolean) => void;
  getCurrentTime: () => number;
  playVideo: () => void;
  destroy: () => void;
}

declare global {
  interface Window {
    YT?: {
      Player: new (
        el: HTMLElement,
        opts: Record<string, unknown>,
      ) => YTPlayer;
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

const SCRIPT_ID = "youtube-iframe-api";

// Load the IFrame API exactly once, resolving when window.YT is ready (§16.6).
function loadYouTubeApi(): Promise<void> {
  return new Promise((resolve) => {
    if (window.YT?.Player) {
      resolve();
      return;
    }
    const prev = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      prev?.();
      resolve();
    };
    if (!document.getElementById(SCRIPT_ID)) {
      const tag = document.createElement("script");
      tag.id = SCRIPT_ID;
      tag.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(tag);
    }
  });
}

export const VideoPlayer = forwardRef<
  VideoPlayerHandle,
  { videoId: string; onTime?: (seconds: number) => void }
>(function VideoPlayer({ videoId, onTime }, ref) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  // Keep the latest onTime without re-creating the player on every render.
  const onTimeRef = useRef(onTime);
  onTimeRef.current = onTime;

  useImperativeHandle(
    ref,
    () => ({
      seekTo: (seconds: number) => {
        playerRef.current?.seekTo(seconds, true);
        playerRef.current?.playVideo();
      },
    }),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    let ticker: ReturnType<typeof setInterval> | undefined;

    loadYouTubeApi().then(() => {
      if (cancelled || !hostRef.current || !window.YT) return;
      playerRef.current = new window.YT.Player(hostRef.current, {
        videoId,
        playerVars: { rel: 0, modestbranding: 1, playsinline: 1 },
      });
      // Drive the playhead + active-chapter highlight at 500 ms (§16.6).
      ticker = setInterval(() => {
        const t = playerRef.current?.getCurrentTime?.();
        if (typeof t === "number") onTimeRef.current?.(t);
      }, 500);
    });

    return () => {
      cancelled = true;
      if (ticker) clearInterval(ticker);
      playerRef.current?.destroy();
      playerRef.current = null;
    };
  }, [videoId]);

  return (
    <div className="aspect-video w-full overflow-hidden rounded-lg border border-hairline bg-black">
      {/* The API replaces this node with the player iframe. */}
      <div ref={hostRef} className="h-full w-full" />
    </div>
  );
});
