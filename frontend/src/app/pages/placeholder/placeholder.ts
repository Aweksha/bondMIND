import { Component, input } from '@angular/core';

@Component({
  selector: 'bm-placeholder',
  template: `
    <h1>{{ title() }}</h1>
    <div class="panel">
      <p>
        <strong>Planned for {{ milestone() }}.</strong> {{ summary() }}
      </p>
      <p class="muted">This module is not built yet. Nothing on this page is computed.</p>
    </div>
  `,
})
export class Placeholder {
  readonly title = input('');
  readonly milestone = input('');
  readonly summary = input('');
}
