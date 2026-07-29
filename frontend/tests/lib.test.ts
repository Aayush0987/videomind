import { describe, expect, it } from "vitest";
import { formatTimecode, parseAnswer } from "@/lib/format";
import {
  deserializeLLMConfig,
  serializeLLMConfig,
} from "@/lib/settings";
import type { Citation } from "@/lib/types";

describe("formatTimecode", () => {
  it("renders mm:ss with zero padding", () => {
    expect(formatTimecode(0)).toBe("00:00");
    expect(formatTimecode(9)).toBe("00:09");
    expect(formatTimecode(75)).toBe("01:15");
    expect(formatTimecode(271)).toBe("04:31");
  });

  it("grows to h:mm:ss only past 60 minutes", () => {
    expect(formatTimecode(3599)).toBe("59:59");
    expect(formatTimecode(3600)).toBe("1:00:00");
    expect(formatTimecode(3661)).toBe("1:01:01");
  });

  it("floors fractional seconds and clamps negatives", () => {
    expect(formatTimecode(8.9)).toBe("00:08");
    expect(formatTimecode(-5)).toBe("00:00");
  });
});

describe("parseAnswer", () => {
  const citations: Citation[] = [
    {
      marker: "c0",
      chunk_id: "v:c0",
      start: 271,
      end: 302,
      quote: "the cost scaled linearly",
      chapter_title: "Cost",
    },
  ];

  it("splits prose from resolved citation markers", () => {
    const segs = parseAnswer("It scaled [[c0]] fast.", citations);
    expect(segs).toEqual([
      { kind: "text", text: "It scaled " },
      { kind: "citation", marker: "c0", citation: citations[0] },
      { kind: "text", text: " fast." },
    ]);
  });

  it("keeps a dropped marker with a null citation", () => {
    const segs = parseAnswer("Unknown [[c9]].", citations);
    expect(segs[1]).toEqual({
      kind: "citation",
      marker: "c9",
      citation: null,
    });
  });

  it("returns a single text segment when there are no markers", () => {
    expect(parseAnswer("plain", citations)).toEqual([
      { kind: "text", text: "plain" },
    ]);
  });
});

describe("LLM config serialisation", () => {
  it("round-trips a full config", () => {
    const cfg = {
      provider: "openai" as const,
      model: "gpt-4o",
      api_key: "sk-123",
      base_url: "https://x/v1",
    };
    expect(deserializeLLMConfig(serializeLLMConfig(cfg))).toEqual(cfg);
  });

  it("drops unknown providers and blank fields", () => {
    const raw = JSON.stringify({
      provider: "bogus",
      model: "   ",
      api_key: "",
    });
    expect(deserializeLLMConfig(raw)).toEqual({});
  });

  it("treats null storage as an empty config", () => {
    expect(deserializeLLMConfig(null)).toEqual({});
  });
});
