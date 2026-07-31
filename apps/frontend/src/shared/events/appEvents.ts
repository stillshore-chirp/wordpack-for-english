export const APP_EVENTS = {
  authUnauthorized: 'auth:unauthorized',
  wordPackUpdated: 'wordpack:updated',
  wordPackStudyProgress: 'wordpack:study-progress',
  articleUpdated: 'article:updated',
  quizUpdated: 'quiz:updated',
} as const;

export interface AuthUnauthorizedDetail {
  url: string;
  status: number;
  body: unknown;
}

export interface WordPackStudyProgressDetail {
  wordPackId: string;
  checked_only_count: number;
  learned_count: number;
}

export type AppEventDetailMap = {
  [APP_EVENTS.authUnauthorized]: AuthUnauthorizedDetail;
  [APP_EVENTS.wordPackUpdated]: undefined;
  [APP_EVENTS.wordPackStudyProgress]: WordPackStudyProgressDetail;
  [APP_EVENTS.articleUpdated]: undefined;
  [APP_EVENTS.quizUpdated]: undefined;
};

export const dispatchAppEvent = <Name extends keyof AppEventDetailMap>(
  name: Name,
  detail?: AppEventDetailMap[Name],
): void => {
  try {
    window.dispatchEvent(new CustomEvent(name, detail === undefined ? undefined : { detail }));
  } catch {
    // Browser外環境では何もしない。
  }
};
