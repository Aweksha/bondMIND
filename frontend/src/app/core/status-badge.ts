import { Component, input } from '@angular/core';

/** Status is always conveyed by text + icon, never colour alone (WCAG). */
@Component({
  selector: 'bm-status',
  template: `<span class="badge" [class]="'badge badge--' + status()"
    ><span aria-hidden="true">{{ icon() }}</span> {{ status() }}</span
  >`,
})
export class StatusBadge {
  readonly status = input.required<string>();
  icon() {
    return { fresh: '●', stale: '▲', missing: '✕' }[this.status()] ?? '•';
  }
}
