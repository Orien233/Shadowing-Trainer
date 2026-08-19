import { describe, expect, it } from "vitest";
import type { Sentence } from "../../../types";
import {
  buildTimelineSegments,
  findAdjacentSegmentIndex,
  locateSegmentIndex,
  SEGMENT_EPSILON,
} from "./timeline";

function sentence(id: number, start: number, end: number): Sentence {
  return {
    id,
    material_id: 1,
    display_order: id,
    start_time: start,
    end_time: end,
    original_start_time: null,
    original_end_time: null,
    clip_audio_path: null,
    clip_duration: null,
    source_text: `sentence ${id}`,
    translation: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("timeline domain logic", () => {
  it("creates gaps before, between, and after sentences", () => {
    const segments = buildTimelineSegments([sentence(1, 1, 2), sentence(2, 4, 5)], 7);
    expect(segments.map(({ type, start, end }) => ({ type, start, end }))).toEqual([
      { type: "gap", start: 0, end: 1 },
      { type: "sentence", start: 1, end: 2 },
      { type: "gap", start: 2, end: 4 },
      { type: "sentence", start: 4, end: 5 },
      { type: "gap", start: 5, end: 7 },
    ]);
  });

  it("keeps overlap in order and prefers the latest matching segment", () => {
    const segments = buildTimelineSegments([sentence(1, 1, 4), sentence(2, 3, 5)], 5);
    expect(segments).toHaveLength(3);
    expect(locateSegmentIndex(segments, 3.5)).toBe(2);
    expect(locateSegmentIndex(segments, 1)).toBe(1);
  });

  it("handles boundaries, epsilon-sized clips, and empty materials", () => {
    const short = buildTimelineSegments([sentence(1, 2, 2)], 2 + SEGMENT_EPSILON);
    expect(short[0].duration).toBe(2);
    expect(short[1].duration).toBe(SEGMENT_EPSILON);
    expect(locateSegmentIndex(short, 0)).toBe(0);
    expect(locateSegmentIndex(short, short[short.length - 1].end)).toBe(short.length - 1);

    const empty = buildTimelineSegments([], 3);
    expect(empty).toEqual([{ key: "gap-1-0.000", type: "gap", start: 0, end: 3, duration: 3, sentence: null, displayOrder: 1 }]);
    expect(findAdjacentSegmentIndex([], 0, 1)).toBe(0);
    expect(findAdjacentSegmentIndex(empty, 0, -1)).toBe(0);
  });
});
