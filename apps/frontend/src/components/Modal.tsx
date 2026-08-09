import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  maxWidth?: string;
  closeLabel?: string;
  allowWideView?: boolean;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
}

const DEFAULT_MODAL_MAX_WIDTH = 'min(96vw, calc(var(--main-max-width, 1000px) * 0.90))';
const WIDE_MODAL_MAX_WIDTH = 'min(96vw, calc(var(--main-max-width, 1000px) * 1.80))';

let nextModalId = 0;
const modalStack: number[] = [];
const modalOverlayAttribute = 'data-wordpack-modal-overlay';

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const getFocusableElements = (root: HTMLElement | null): HTMLElement[] => {
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>(focusableSelector)).filter((element) => {
    if (element.getAttribute('aria-hidden') === 'true') return false;
    if (element.hasAttribute('disabled')) return false;
    const computedStyle = window.getComputedStyle(element);
    if (computedStyle.display === 'none') return false;
    if (computedStyle.visibility === 'hidden' || computedStyle.visibility === 'collapse') return false;
    return true;
  });
};

const isTopmostModal = (id: number) => modalStack[modalStack.length - 1] === id;

const isModalOverlayElement = (element: Element): element is HTMLElement =>
  element instanceof HTMLElement && element.hasAttribute(modalOverlayAttribute);

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  maxWidth,
  closeLabel,
  allowWideView = false,
  initialFocusRef,
  returnFocusRef,
}) => {
  const dialogTitleId = useId();
  const overlayRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const [isWideView, setIsWideView] = useState(false);
  const modalIdRef = useRef<number>(0);
  if (modalIdRef.current === 0) {
    nextModalId += 1;
    modalIdRef.current = nextModalId;
  }

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen || !allowWideView) {
      setIsWideView(false);
    }
  }, [allowWideView, isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const modalId = modalIdRef.current;
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    modalStack.push(modalId);

    const overlay = overlayRef.current;
    if (overlay) {
      overlay.removeAttribute('aria-hidden');
      (overlay as HTMLElement & { inert?: boolean }).inert = false;
    }

    const parent = overlay?.parentElement ?? null;
    const siblings = parent
      ? Array.from(parent.children).filter((child) => child !== overlay && !isModalOverlayElement(child))
      : [];
    const previousSiblingStates = siblings.map((element) => ({
      element: element as HTMLElement,
      ariaHidden: element.getAttribute('aria-hidden'),
      inert: Boolean((element as HTMLElement & { inert?: boolean }).inert),
    }));
    previousSiblingStates.forEach(({ element }) => {
      element.setAttribute('aria-hidden', 'true');
      (element as HTMLElement & { inert?: boolean }).inert = true;
    });

    const focusInitialElement = () => {
      if (!isTopmostModal(modalId)) return;
      const target =
        initialFocusRef?.current ??
        closeButtonRef.current ??
        getFocusableElements(panelRef.current)[0] ??
        panelRef.current;
      target?.focus();
    };
    const focusFrame = window.requestAnimationFrame(focusInitialElement);

    const onKey = (e: KeyboardEvent) => {
      if (!isTopmostModal(modalId)) return;
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab') return;
      const focusable = getFocusableElements(panelRef.current);
      if (focusable.length === 0) {
        e.preventDefault();
        panelRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      window.removeEventListener('keydown', onKey);
      const index = modalStack.lastIndexOf(modalId);
      if (index >= 0) modalStack.splice(index, 1);
      previousSiblingStates.forEach(({ element, ariaHidden, inert }) => {
        if (ariaHidden === null) {
          element.removeAttribute('aria-hidden');
        } else {
          element.setAttribute('aria-hidden', ariaHidden);
        }
        (element as HTMLElement & { inert?: boolean }).inert = inert;
      });
      const returnTarget = returnFocusRef?.current ?? previouslyFocusedRef.current;
      if (returnTarget?.isConnected) {
        returnTarget.focus();
      }
    };
  }, [initialFocusRef, isOpen, returnFocusRef]);

  if (!isOpen) return null;
  const resolvedTitle = title || 'モーダル';
  const resolvedCloseLabel = closeLabel || `${resolvedTitle}を閉じる`;
  const resolvedMaxWidth = allowWideView && isWideView
    ? WIDE_MODAL_MAX_WIDTH
    : maxWidth ?? DEFAULT_MODAL_MAX_WIDTH;
  const modalContent = (
    <div
      ref={overlayRef}
      data-wordpack-modal-overlay="true"
      role="dialog"
      aria-modal="true"
      aria-labelledby={dialogTitleId}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'var(--color-inverse-overlay)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: '1rem',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && isTopmostModal(modalIdRef.current)) onClose();
      }}
   >
      <div
        ref={panelRef}
        data-modal-panel="true"
        tabIndex={-1}
        style={{
          width: '100%',
          maxWidth: resolvedMaxWidth,
          maxHeight: '90vh',
          overflow: 'auto',
          background: 'var(--color-surface)',
          borderRadius: 8,
          boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
        }}
      >
        {allowWideView ? (
          <style>{`
            @media (max-width: 960px) {
              .modal-width-toggle { display: none; }
            }
          `}</style>
        ) : null}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1rem', borderBottom: '1px solid var(--color-border)' }}>
          <strong id={dialogTitleId} style={{ flex: '1 1 auto', minWidth: 0, overflowWrap: 'anywhere', fontSize: '1.1rem' }}>{resolvedTitle}</strong>
          <div style={{ display: 'inline-flex', flex: '0 0 auto', alignItems: 'center', gap: '0.5rem' }}>
            {allowWideView ? (
              <button
                type="button"
                className="modal-width-toggle"
                aria-pressed={isWideView}
                onClick={() => setIsWideView((current) => !current)}
                style={{
                  minHeight: '2.25rem',
                  paddingInline: '0.75rem',
                  borderColor: isWideView ? 'var(--color-accent)' : undefined,
                  background: isWideView ? 'var(--color-accent-bg)' : undefined,
                  color: isWideView ? 'var(--color-accent)' : undefined,
                }}
              >
                ワイド表示
              </button>
            ) : null}
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              aria-label={resolvedCloseLabel}
            >
              閉じる
            </button>
          </div>
        </div>
        <div style={{ padding: '1rem' }}>
          {children}
        </div>
      </div>
    </div>
  );
  return createPortal(modalContent, document.body);
};


