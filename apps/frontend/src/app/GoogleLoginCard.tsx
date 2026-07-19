import React from 'react';
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google';
import { useAuth } from '../AuthContext';
import { LoadingIndicator } from '../components/LoadingIndicator';
import { sendMissingIdTokenTelemetry } from '../features/auth/googleTelemetry';

interface GoogleLoginCardProps {
  title: string;
  isAuthenticating: boolean;
  clearError: () => void;
  error: string | null;
  localError: string | null;
  setLocalError: React.Dispatch<React.SetStateAction<string | null>>;
  signIn: (idToken: string) => Promise<void>;
  googleClientId: string;
}

export const GoogleLoginCard: React.FC<GoogleLoginCardProps> = ({
  title,
  isAuthenticating,
  clearError,
  error,
  localError,
  setLocalError,
  signIn,
  googleClientId,
}) => {
  const { enterGuestMode } = useAuth();
  const handleCredentialSuccess = async (credentialResponse: CredentialResponse) => {
    const idToken = credentialResponse?.credential;
    if (!idToken) {
      console.warn('Google login succeeded without an ID token', credentialResponse);
      void sendMissingIdTokenTelemetry(googleClientId, credentialResponse);
      setLocalError('ID トークンを取得できませんでした。ブラウザを更新して再試行してください。');
      return;
    }
    try {
      await signIn(idToken);
      setLocalError(null);
    } catch (err) {
      console.warn('Sign-in request rejected', err);
    }
  };

  const handleCredentialError = () => {
    setLocalError('Google サインインでエラーが発生しました。時間を置いて再試行してください。');
  };

  const handleBeforeGoogleInteraction = () => {
    clearError();
    setLocalError(null);
  };

  const googleButtonTheme =
    typeof document !== 'undefined' && document.body.classList.contains('theme-dark')
      ? 'filled_black'
      : 'filled_blue';
  const combinedError = localError || error;

  return (
    <section className="login-card" role="dialog" aria-labelledby="login-title" aria-live="polite">
      <h2 id="login-title" className="login-title">{title}</h2>
      <p className="login-description">Google アカウントでログインして辞書データと設定を同期します。</p>
      {combinedError ? (
        <div role="alert" className="login-error">
          {combinedError}
        </div>
      ) : null}
      <div
        className="login-google-button"
        onClickCapture={handleBeforeGoogleInteraction}
        style={{
          pointerEvents: isAuthenticating ? 'none' : 'auto',
          opacity: isAuthenticating ? 0.72 : 1,
        }}
      >
        <GoogleLogin
          onSuccess={handleCredentialSuccess}
          onError={handleCredentialError}
          useOneTap={false}
          theme={googleButtonTheme as 'filled_black' | 'filled_blue'}
          text="signin_with"
          shape="pill"
          width="320"
          context="signin"
        />
      </div>
      <p className="login-note">成功するとブラウザにセッションクッキーを保存します。</p>
      <button
        type="button"
        className="login-guest-button"
        onClick={() => {
          void enterGuestMode();
        }}
      >
        ゲスト閲覧モード
      </button>
      {isAuthenticating ? (
        <div className="login-progress">
          <LoadingIndicator label="認証処理中" subtext="Google の応答を検証しています" />
        </div>
      ) : null}
    </section>
  );
};
