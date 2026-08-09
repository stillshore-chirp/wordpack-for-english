import React, { useMemo, useRef } from 'react';
import { Modal } from './Modal';
import { WordPackPanel, type WordPackPreviewMeta } from './WordPackPanel';
import type { WordPackListItem } from '../features/wordpack/types';

interface WordPackPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  wordPackId: string | null;
  wordPacks: WordPackListItem[];
  onWordPackUpdated?: () => void;
  onStudyProgressRecorded?: (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => void;
  contextLabel?: string;
  contextDescription?: string;
  notice?: React.ReactNode;
  navigationIds?: string[];
  onNavigate?: (wordPackId: string) => void;
}

export const WordPackPreviewModal: React.FC<WordPackPreviewModalProps> = ({
  isOpen,
  onClose,
  wordPackId,
  wordPacks,
  onWordPackUpdated,
  onStudyProgressRecorded,
  contextLabel,
  contextDescription,
  notice,
  navigationIds,
  onNavigate,
}) => {
  const focusRef = useRef<HTMLElement>(null);
  const previewMeta = useMemo<WordPackPreviewMeta | null>(() => {
    if (!wordPackId) return null;
    const meta = wordPacks.find((wordPack) => wordPack.id === wordPackId);
    if (!meta) return null;
    return {
      id: meta.id,
      lemma: meta.lemma,
      senseTitle: meta.sense_title,
      created_at: meta.created_at,
      updated_at: meta.updated_at,
    };
  }, [wordPackId, wordPacks]);
  const lemmaLabel = previewMeta?.lemma?.trim() || previewMeta?.senseTitle?.trim() || 'WordPack';
  const title = contextLabel
    ? `${contextLabel}: ${lemmaLabel}`
    : `WordPack プレビュー: ${lemmaLabel}`;
  const navigationState = useMemo(() => {
    if (!wordPackId || !navigationIds?.length) return null;
    const currentIndex = navigationIds.indexOf(wordPackId);
    if (currentIndex < 0) return null;
    return {
      currentIndex,
      total: navigationIds.length,
      previousId: currentIndex > 0 ? navigationIds[currentIndex - 1] : null,
      nextId: currentIndex < navigationIds.length - 1 ? navigationIds[currentIndex + 1] : null,
    };
  }, [navigationIds, wordPackId]);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      closeLabel="WordPackプレビューを閉じる"
      allowWideView
    >
      {wordPackId ? (
        <>
          <style>{`
            .wordpack-preview-modal__toolbar { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
            .wordpack-preview-modal__context { margin: 0; color: var(--color-subtle); }
            .wordpack-preview-modal__nav { display: inline-flex; align-items: center; gap: 0.5rem; margin-left: auto; }
            .wordpack-preview-modal__nav button { min-height: 2rem; padding: 0.25rem 0.7rem; }
            .wordpack-preview-modal__position { color: var(--color-subtle); font-size: 0.9rem; }
          `}</style>
          {(contextDescription || navigationState) ? (
            <div className="wordpack-preview-modal__toolbar">
              {contextDescription ? (
                <p className="wordpack-preview-modal__context">{contextDescription}</p>
              ) : <span />}
              {navigationState ? (
                <div className="wordpack-preview-modal__nav" aria-label="プレビュー移動">
                  <button
                    type="button"
                    onClick={() => {
                      if (navigationState.previousId) onNavigate?.(navigationState.previousId);
                    }}
                    disabled={!navigationState.previousId || !onNavigate}
                  >
                    前へ
                  </button>
                  <span className="wordpack-preview-modal__position">
                    {navigationState.currentIndex + 1} / {navigationState.total}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (navigationState.nextId) onNavigate?.(navigationState.nextId);
                    }}
                    disabled={!navigationState.nextId || !onNavigate}
                  >
                    次へ
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}
          <WordPackPanel
            focusRef={focusRef}
            selectedWordPackId={wordPackId}
            selectedMeta={
              previewMeta?.created_at && previewMeta?.updated_at
                ? { created_at: previewMeta.created_at, updated_at: previewMeta.updated_at }
                : null
            }
            fallbackMeta={previewMeta ? { id: previewMeta.id, lemma: previewMeta.lemma, senseTitle: previewMeta.senseTitle } : null}
            onWordPackGenerated={() => {
              onWordPackUpdated?.();
            }}
            onStudyProgressRecorded={onStudyProgressRecorded}
            previewNotice={notice}
            revealStudyCardImmediately
            onRequestClose={onClose}
          />
        </>
      ) : null}
    </Modal>
  );
};
