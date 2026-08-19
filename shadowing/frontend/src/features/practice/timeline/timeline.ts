import type { Sentence } from "../../../types";

export type SegmentType = "sentence" | "gap";

export interface TimelineSegment {
  key: string;
  type: SegmentType;
  start: number;
  end: number;
  duration: number;
  sentence: Sentence | null;
  displayOrder: number;
}

export const SEGMENT_EPSILON = 0.05;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function getSentenceStart(sentence: Sentence): number {
  if (Number.isFinite(sentence.start_time)) return sentence.start_time;
  return sentence.original_start_time ?? 0;
}

export function getSentenceEnd(sentence: Sentence): number {
  if (Number.isFinite(sentence.end_time)) return sentence.end_time;
  return sentence.original_end_time ?? getSentenceStart(sentence) + SEGMENT_EPSILON;
}

export function buildTimelineSegments(sentences: Sentence[], timelineDuration: number): TimelineSegment[] {
  const segments: TimelineSegment[] = [];
  let cursor = 0;
  let gapOrder = 0;

  for (const sentence of sentences) {
    const sentenceStart = Math.max(getSentenceStart(sentence), 0);
    const sentenceEnd = Math.max(getSentenceEnd(sentence), sentenceStart + SEGMENT_EPSILON);

    if (sentenceStart - cursor > SEGMENT_EPSILON) {
      gapOrder += 1;
      segments.push({
        key: `gap-${gapOrder}-${cursor.toFixed(3)}`,
        type: "gap",
        start: cursor,
        end: sentenceStart,
        duration: sentenceStart - cursor,
        sentence: null,
        displayOrder: gapOrder,
      });
    }

    const sentenceDuration = Math.max(sentenceEnd - sentenceStart, SEGMENT_EPSILON);
    segments.push({
      key: `sentence-${sentence.id}`,
      type: "sentence",
      start: sentenceStart,
      end: sentenceStart + sentenceDuration,
      duration: sentenceDuration,
      sentence,
      displayOrder: sentence.display_order,
    });
    cursor = Math.max(cursor, sentenceStart + sentenceDuration);
  }

  if (timelineDuration - cursor > SEGMENT_EPSILON) {
    gapOrder += 1;
    segments.push({
      key: `gap-${gapOrder}-${cursor.toFixed(3)}`,
      type: "gap",
      start: cursor,
      end: timelineDuration,
      duration: timelineDuration - cursor,
      sentence: null,
      displayOrder: gapOrder,
    });
  }

  if (segments.length === 0 && timelineDuration > SEGMENT_EPSILON) {
    segments.push({ key: "gap-1-0", type: "gap", start: 0, end: timelineDuration, duration: timelineDuration, sentence: null, displayOrder: 1 });
  }
  return segments;
}

export function locateSegmentIndex(segments: TimelineSegment[], time: number): number {
  if (segments.length === 0) return 0;
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const segment = segments[i];
    const isLast = i === segments.length - 1;
    if (time >= segment.start && (time < segment.end || (isLast && time <= segment.end + SEGMENT_EPSILON))) return i;
  }
  if (time < segments[0].start) return 0;
  return segments.length - 1;
}

export function findAdjacentSegmentIndex(segments: TimelineSegment[], fromIndex: number, direction: -1 | 1): number {
  if (segments.length === 0) return 0;
  return clamp(fromIndex + direction, 0, segments.length - 1);
}
