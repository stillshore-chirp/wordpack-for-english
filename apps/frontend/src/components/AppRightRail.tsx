import React from 'react';
import { GenerationQueuePanel } from './GenerationQueuePanel';
import { Badge } from '../shared/ui';

interface AppRightRailProps {
  children?: React.ReactNode;
  label?: string;
}

interface RailCardProps {
  title: string;
  badge?: string;
  children: React.ReactNode;
}

export const RailCard: React.FC<RailCardProps> = ({
  title,
  badge,
  children,
}) => (
  <section className="dictionary-rail-card">
    <div className="dictionary-rail-card__header">
      <h2>{title}</h2>
      {badge ? <Badge variant="accent">{badge}</Badge> : null}
    </div>
    {children}
  </section>
);

export const AppRightRail: React.FC<AppRightRailProps> = ({
  children,
  label = '生成と作業状況',
}) => (
  <div
    className="dictionary-rail"
    role="region"
    aria-label={label}
    tabIndex={0}
  >
    <GenerationQueuePanel />
    {children}
  </div>
);
