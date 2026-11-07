import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

interface NavItem {
  path: string;
  label: string;
  milestone?: string;
}

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <a class="skip-link" href="#main">Skip to content</a>
    <div class="shell">
      <aside class="sidebar">
        <div class="brand">bond<span>MIND</span> <small>AI</small></div>
        <nav aria-label="Primary">
          @for (item of nav; track item.path) {
            <a [routerLink]="item.path" routerLinkActive="active" ariaCurrentWhenActive="page">
              {{ item.label }}
              @if (item.milestone) {
                <span class="soon">{{ item.milestone }}</span>
              }
            </a>
          }
        </nav>
      </aside>
      <div class="content">
        <header class="topbar">
          <span class="env-badge" role="status">
            DEMO · SYNTHETIC DATA. These are not market observations.
          </span>
          <span class="disclaimer">Research tool only. Not investment advice.</span>
        </header>
        <main id="main" tabindex="-1"><router-outlet /></main>
      </div>
    </div>
  `,
})
export class App {
  protected readonly nav: NavItem[] = [
    { path: '/overview', label: 'Overview' },
    { path: '/screener', label: 'Screener' },
    { path: '/curves', label: 'Yield Curves', milestone: 'M1' },
    { path: '/signals', label: 'AI Signals', milestone: 'M2' },
    { path: '/credit', label: 'Credit Intelligence', milestone: 'M2' },
    { path: '/watchlists', label: 'Watchlists', milestone: 'M3' },
    { path: '/portfolio', label: 'Portfolio Lab', milestone: 'M3' },
    { path: '/data', label: 'Data / Models' },
  ];
}
