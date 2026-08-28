import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { buildLanguageParagraphs, buildSentenceAlignment } from './sentenceAlignment';

interface AlignmentFixture {
  name: string;
  body_en: string;
  body_ja: string;
  english_sentence_counts: number[];
  japanese_sentence_counts: number[];
}

const fixtures = JSON.parse(readFileSync(
  resolve(process.cwd(), '../../tests/fixtures/quiz_sentence_alignment.json'),
  'utf8',
)) as AlignmentFixture[];

describe('deterministic sentence alignment', () => {
  it.each(fixtures)('matches the shared backend fixture: $name', (fixture) => {
    const english = buildLanguageParagraphs(fixture.body_en, 'en');
    const japanese = buildLanguageParagraphs(fixture.body_ja, 'ja');

    expect(english.map((paragraph) => paragraph.sentences.length))
      .toEqual(fixture.english_sentence_counts);
    expect(japanese.map((paragraph) => paragraph.sentences.length))
      .toEqual(fixture.japanese_sentence_counts);
  });

  it('keeps legacy segmentation by default and opts new quizzes into deterministic v1', () => {
    const bodyEn = 'Wait!Really? Next.';
    const bodyJa = '待って！本当に？次です。';

    expect(buildSentenceAlignment(bodyEn, bodyJa).englishParagraphs[0].sentences)
      .toHaveLength(3);
    expect(buildSentenceAlignment(bodyEn, bodyJa, 'deterministic').englishParagraphs[0].sentences)
      .toHaveLength(2);
  });
});
