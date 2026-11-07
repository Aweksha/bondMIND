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
    path: 'terminal',
    title: 'Terminal · bondMIND',
    loadComponent: () => import('./pages/terminal/terminal').then((m) => m.Terminal),
  },
  {
    path: 'terminal/security/:id',
    title: 'Terminal · bondMIND',
    loadComponent: () => import('./pages/terminal/terminal').then((m) => m.Terminal),
  },
  {
    path: 'curve-lab',
    title: 'Curve Lab · bondMIND',
    loadComponent: () => import('./pages/curve-lab/curve-lab').then((m) => m.CurveLab),
  },
  { path: 'securities/:id', redirectTo: 'terminal/security/:id' },
  { path: 'curves', redirectTo: 'curve-lab' },
  {
    path: 'data',
    title: 'Data / Models · bondMIND',
    loadComponent: () => import('./pages/data-quality/data-quality').then((m) => m.DataQuality),
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
