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
            DEMO · Synthetic bonds &amp; quotes · Real U.S. Treasury curve
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
    { path: '/terminal', label: 'Terminal' },
    { path: '/curve-lab', label: 'Curve Lab' },
    { path: '/screener', label: 'Screener' },
    { path: '/signals', label: 'AI Signals', milestone: 'later' },
    { path: '/credit', label: 'Credit Intelligence', milestone: 'later' },
    { path: '/watchlists', label: 'Watchlists', milestone: 'later' },
    { path: '/portfolio', label: 'Portfolio Lab', milestone: 'later' },
    { path: '/data', label: 'Data / Models' },
  ];
}
