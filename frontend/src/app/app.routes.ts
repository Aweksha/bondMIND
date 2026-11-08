import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'bonds' },
  {
    path: 'bonds',
    title: 'Bond Explorer · bondMIND',
    loadComponent: () => import('./pages/bonds/bond-explorer').then((m) => m.BondExplorer),
  },
  {
    path: 'bonds/:id',
    title: 'Bond · bondMIND',
    loadComponent: () => import('./pages/bonds/bond-detail').then((m) => m.BondDetail),
  },
  {
    path: 'yield-curve',
    title: 'Yield Curve · bondMIND',
    loadComponent: () => import('./pages/yield-curve/yield-curve').then((m) => m.YieldCurve),
  },
  {
    path: 'simulator',
    title: 'Price Simulator · bondMIND',
    loadComponent: () => import('./pages/simulator/simulator').then((m) => m.Simulator),
  },
  {
    path: 'data',
    title: 'Data sources · bondMIND',
    loadComponent: () => import('./pages/data-quality/data-quality').then((m) => m.DataQuality),
  },
  // Old links keep working
  { path: 'terminal/security/:id', redirectTo: 'bonds/:id' },
  { path: 'securities/:id', redirectTo: 'bonds/:id' },
  { path: 'screener', redirectTo: 'bonds' },
  { path: 'terminal', redirectTo: 'bonds' },
  { path: 'curve-lab', redirectTo: 'yield-curve' },
  { path: '**', redirectTo: 'bonds' },
];
