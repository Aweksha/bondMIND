import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <a class="skip-link" href="#main">Skip to content</a>
    <header class="appbar">
      <a class="brand" routerLink="/bonds">bond<span>MIND</span></a>
      <nav aria-label="Primary" class="tabs">
        @for (item of nav; track item.path) {
          <a [routerLink]="item.path" routerLinkActive="active" ariaCurrentWhenActive="page">{{
            item.label
          }}</a>
        }
      </nav>
    </header>
    <div class="data-note" role="note">
      Bonds &amp; quotes are <strong>synthetic</strong> demo data · Treasury curve is
      <strong>real</strong> (U.S. Treasury)
    </div>
    <main id="main" tabindex="-1"><router-outlet /></main>
    <footer class="site-footer">
      <span>bondMIND · educational research tool. Not investment advice.</span>
      <a routerLink="/data">Data sources &amp; quality</a>
    </footer>
  `,
})
export class App {
  protected readonly nav = [
    { path: '/bonds', label: 'Bond Explorer' },
    { path: '/yield-curve', label: 'Yield Curve' },
    { path: '/simulator', label: 'Price Simulator' },
  ];
}
