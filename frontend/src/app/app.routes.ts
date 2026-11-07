import { Routes } from '@angular/router';

const placeholder = (title: string, milestone: string, summary: string) => ({
  loadComponent: () => import('./pages/placeholder/placeholder').then((m) => m.Placeholder),
  data: { title, milestone, summary },
  title: `${title} · bondMIND`,
});

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'overview' },
  {
    path: 'overview',
    title: 'Overview · bondMIND',
    loadComponent: () => import('./pages/overview/overview').then((m) => m.Overview),
  },
  {
    path: 'screener',
    title: 'Screener · bondMIND',
    loadComponent: () => import('./pages/screener/screener').then((m) => m.Screener),
  },
  {
    path: 'securities/:id',
    title: 'Security · bondMIND',
    loadComponent: () => import('./pages/security/security').then((m) => m.SecurityPage),
  },
  {
    path: 'data',
    title: 'Data / Models · bondMIND',
    loadComponent: () => import('./pages/data-quality/data-quality').then((m) => m.DataQuality),
  },
  {
    path: 'curves',
    ...placeholder('Yield Curve Lab', 'M1', 'Curve chart, interpolation, history and shocks.'),
  },
  {
    path: 'signals',
    ...placeholder(
      'AI Signals',
      'M2',
      'Ranked research signals with horizon, intervals, drivers and backtest context. ' +
        'Built only after a model passes walk-forward validation.',
    ),
  },
  {
    path: 'credit',
    ...placeholder('Credit Intelligence', 'M2', 'Rating history and credit indicators.'),
  },
  {
    path: 'watchlists',
    ...placeholder('Watchlists', 'M3', 'Create lists, add securities, notes, snapshots.'),
  },
  {
    path: 'portfolio',
    ...placeholder('Portfolio Lab', 'M3', 'Holdings, exposures, DV01 and shock P&L.'),
  },
  { path: '**', redirectTo: 'overview' },
];
