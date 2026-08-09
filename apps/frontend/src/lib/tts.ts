import { TTS_API_REQUEST_MAX_LENGTH } from '../constants/tts';

const MIN_PREFERRED_BOUNDARY_RATIO = 0.5;

const isHighSurrogate = (value: number): boolean => value >= 0xD800 && value <= 0xDBFF;
const isLowSurrogate = (value: number): boolean => value >= 0xDC00 && value <= 0xDFFF;

const preserveSurrogatePairAtBoundary = (value: string, boundary: number): number => {
  if (
    boundary > 0
    && boundary < value.length
    && isHighSurrogate(value.charCodeAt(boundary - 1))
    && isLowSurrogate(value.charCodeAt(boundary))
  ) {
    return boundary - 1;
  }
  return boundary;
};

const lastMatchEnd = (value: string, pattern: RegExp): number => {
  pattern.lastIndex = 0;
  let end = -1;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(value)) !== null) {
    end = match.index + match[0].length;
  }
  return end;
};

const findPreferredBoundary = (value: string, maxLength: number): number => {
  const minimum = Math.floor(maxLength * MIN_PREFERRED_BOUNDARY_RATIO);
  const patterns = [
    /\n\s*\n/g,
    /[.!?。！？]["'’”）)\]]?(?:\s+|$)/g,
    /\s+/g,
  ];

  for (const pattern of patterns) {
    const boundary = lastMatchEnd(value, pattern);
    if (boundary >= minimum && boundary <= maxLength) {
      return boundary;
    }
  }
  return maxLength;
};

/**
 * 保存済み本文の総文字数は制限せず、Speech APIの単発上限以下へ分割する。
 * 段落、文末、空白の順で境界を探し、語や文の途中での分割をできるだけ避ける。
 */
export const splitTextForTts = (
  text: string,
  maxLength = TTS_API_REQUEST_MAX_LENGTH,
): string[] => {
  if (!Number.isInteger(maxLength) || maxLength < 1) {
    throw new RangeError('TTS chunk length must be a positive integer');
  }

  let remaining = text.trim();
  if (!remaining) return [];

  const chunks: string[] = [];
  while (remaining.length > maxLength) {
    const window = remaining.slice(0, maxLength);
    const preferredBoundary = findPreferredBoundary(window, maxLength);
    const adjustedBoundary = preserveSurrogatePairAtBoundary(remaining, preferredBoundary);
    // maxLength=1 かつ先頭がサロゲートペアの場合も、不正な片割れを生成しない。
    const boundary = adjustedBoundary > 0
      ? adjustedBoundary
      : Array.from(remaining)[0]?.length ?? 1;
    chunks.push(remaining.slice(0, boundary));
    remaining = remaining.slice(boundary);
  }
  if (remaining) chunks.push(remaining);
  return chunks;
};
