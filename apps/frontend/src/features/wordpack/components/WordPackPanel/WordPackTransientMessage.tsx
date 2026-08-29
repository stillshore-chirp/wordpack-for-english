import React from 'react';
import type { WordPackMessage } from '../../../../hooks/useWordPack';

interface WordPackTransientMessageProps {
  message: Exclude<WordPackMessage, null> | null;
  announcementKey: number;
}

export const WordPackTransientMessage: React.FC<WordPackTransientMessageProps> = ({ message, announcementKey }) => {
  const successMessage = message?.kind === 'status' ? message : null;
  const errorMessage = message?.kind === 'alert' ? message : null;

  return (
    <>
      <div
        className={`wp-transient-message is-status${successMessage ? '' : ' is-empty visually-hidden'}`}
        role="status"
        aria-label="例文コピー結果"
        aria-live="polite"
        aria-atomic="true"
      >
        {successMessage ? (
          <>
            <span className="wp-transient-message__icon" aria-hidden="true">✓</span>
            <span key={`status-${announcementKey}`}>{successMessage.text}</span>
          </>
        ) : null}
      </div>
      <div
        className={`wp-transient-message is-alert${errorMessage ? '' : ' is-empty visually-hidden'}`}
        role="alert"
        aria-label="例文コピーエラー"
        aria-live="assertive"
        aria-atomic="true"
      >
        {errorMessage ? (
          <>
            <span className="wp-transient-message__icon" aria-hidden="true">!</span>
            <span key={`alert-${announcementKey}`}>{errorMessage.text}</span>
          </>
        ) : null}
      </div>
    </>
  );
};
