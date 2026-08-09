import { describe, expect, it } from 'vitest';
import { TTS_API_REQUEST_MAX_LENGTH } from '../constants/tts';
import { splitTextForTts } from './tts';

describe('splitTextForTts', () => {
  it('keeps text above the former 500-character limit in one API request when possible', () => {
    const text = 'a'.repeat(501);

    expect(splitTextForTts(text)).toEqual([text]);
  });

  it('prefers a sentence boundary before the per-request limit', () => {
    expect(splitTextForTts('First sentence. Second sentence.', 20)).toEqual([
      'First sentence. ',
      'Second sentence.',
    ]);
  });

  it('preserves whitespace at selected boundaries without dropping or duplicating text', () => {
    const text = 'First paragraph.\n\nSecond paragraph with more words.';
    const chunks = splitTextForTts(text, 32);

    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks.every((chunk) => chunk.length <= 32)).toBe(true);
    expect(chunks.join('')).toBe(text);
  });

  it('hard-splits uninterrupted text without dropping content', () => {
    const text = 'a'.repeat(TTS_API_REQUEST_MAX_LENGTH + 25);
    const chunks = splitTextForTts(text);

    expect(chunks).toHaveLength(2);
    expect(chunks.every((chunk) => chunk.length <= TTS_API_REQUEST_MAX_LENGTH)).toBe(true);
    expect(chunks.join('')).toBe(text);
  });

  it('does not split an astral Unicode character across API chunks', () => {
    const text = `${'a'.repeat(TTS_API_REQUEST_MAX_LENGTH - 1)}😀tail`;
    const chunks = splitTextForTts(text);
    const hasUnpairedSurrogate = (value: string): boolean => {
      for (let index = 0; index < value.length; index += 1) {
        const codeUnit = value.charCodeAt(index);
        if (isNaN(codeUnit)) return true;
        if (codeUnit >= 0xD800 && codeUnit <= 0xDBFF) {
          const next = value.charCodeAt(index + 1);
          if (!(next >= 0xDC00 && next <= 0xDFFF)) return true;
          index += 1;
        } else if (codeUnit >= 0xDC00 && codeUnit <= 0xDFFF) {
          return true;
        }
      }
      return false;
    };

    expect(chunks).toHaveLength(2);
    expect(chunks.every((chunk) => chunk.length <= TTS_API_REQUEST_MAX_LENGTH)).toBe(true);
    expect(chunks.every((chunk) => !hasUnpairedSurrogate(chunk))).toBe(true);
    expect(chunks.join('')).toBe(text);
  });
});
