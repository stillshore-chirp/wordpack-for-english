import { renderHook, act } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { useWordPackForm } from '../useWordPackForm';
import { Settings } from '../../SettingsContext';

const baseSettings: Settings = {
  apiBase: '/api',
  pronunciationEnabled: true,
  regenerateScope: 'all',
  autoAdvanceAfterGrade: false,
  requestTimeoutMs: 30000,
  model: 'gpt-5.6-luna',
  reasoningEffort: 'high',
  textVerbosity: 'medium',
  theme: 'light',
  ttsPlaybackRate: 1,
  ttsVolume: 1,
};

describe('useWordPackForm', () => {
  it('validates lemma boundaries and normalization', () => {
    const { result } = renderHook(({ settings }) => {
      const [currentSettings, setCurrentSettings] = useState(settings);
      const form = useWordPackForm({ settings: currentSettings, setSettings: setCurrentSettings });
      return { form };
    }, { initialProps: { settings: baseSettings } });

    expect(result.current.form.lemmaValidation.valid).toBe(false);
    expect(result.current.form.lemmaValidation.message).toBe('見出し語を入力してください（英数字・ハイフン・アポストロフィ・半角スペースのみ）');

    act(() => {
      result.current.form.setLemma('a'.repeat(65));
    });
    expect(result.current.form.lemmaValidation.valid).toBe(false);
    expect(result.current.form.lemmaValidation.message).toBe('見出し語は最大64文字までです（英数字・半角スペース・ハイフン・アポストロフィのみ）');

    act(() => {
      result.current.form.setLemma('invalid!');
    });
    expect(result.current.form.lemmaValidation.valid).toBe(false);
    expect(result.current.form.lemmaValidation.message).toBe('英数字と半角スペース、ハイフン、アポストロフィのみ利用できます');

    act(() => {
      result.current.form.setLemma(` ${'a'.repeat(64)} `);
    });
    expect(result.current.form.lemmaValidation.valid).toBe(true);
    expect(result.current.form.lemmaValidation.normalizedLemma.length).toBe(64);
    expect(result.current.form.lemmaValidation.message).toBe('英数字・半角スペース・ハイフン・アポストロフィのみ（最大64文字）');
  });

  it('updates model and advanced settings together with context', () => {
    const { result } = renderHook(({ settings }) => {
      const [currentSettings, setCurrentSettings] = useState(settings);
      const form = useWordPackForm({ settings: currentSettings, setSettings: setCurrentSettings });
      return { form, currentSettings };
    }, { initialProps: { settings: baseSettings } });

    expect(result.current.form.showAdvancedModelOptions).toBe(true);

    act(() => {
      result.current.form.handleChangeModel('gpt-5.6-luna');
    });
    expect(result.current.form.model).toBe('gpt-5.6-luna');
    expect(result.current.form.showAdvancedModelOptions).toBe(true);
    expect(result.current.currentSettings.model).toBe('gpt-5.6-luna');

    act(() => {
      result.current.form.advancedSettings.handleChangeReasoningEffort('high');
      result.current.form.advancedSettings.handleChangeTextVerbosity('high');
    });
    expect(result.current.form.advancedSettings.reasoningEffort).toBe('high');
    expect(result.current.form.advancedSettings.textVerbosity).toBe('high');
    expect(result.current.currentSettings.reasoningEffort).toBe('high');
    expect(result.current.currentSettings.textVerbosity).toBe('high');
  });
});
