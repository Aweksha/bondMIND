import { DatePipe, JsonPipe, KeyValuePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';

import { ApiErrorBody, DataQualityReport } from '../../core/api.models';
import { ApiService } from '../../core/api.service';
import { StatusBadge } from '../../core/status-badge';

@Component({
  selector: 'bm-data-quality',
  imports: [DatePipe, JsonPipe, KeyValuePipe, StatusBadge],
  template: `
    <h1>Data / Models</h1>
    @if (error(); as e) {
      <div class="panel error" role="alert">{{ e.message }}</div>
    } @else if (report(); as r) {
      <section class="panel" aria-labelledby="ing-h">
        <h2 id="ing-h">Ingestion and freshness</h2>
        <table class="data">
          <thead>
            <tr>
              <th>Dataset</th>
              <th class="num">Loaded</th>
              <th class="num">Rejected</th>
              <th>Last as-of</th>
              <th>Loaded at</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            @for (f of r.freshness; track f.dataset) {
              <tr>
                <td>
                  {{ f.dataset }}
                  @if (f.is_synthetic) {
                    <span class="tag">synthetic</span>
                  }
                </td>
                <td class="num">{{ f.rows_loaded }}</td>
                <td class="num">{{ f.rows_rejected }}</td>
                <td>{{ f.last_as_of ?? '—' }}</td>
                <td>{{ f.last_loaded_at | date: 'short' }}</td>
                <td><bm-status [status]="f.status" /></td>
              </tr>
            }
          </tbody>
        </table>
      </section>

      <section class="panel" aria-labelledby="q-h">
        <h2 id="q-h">Quarantined records</h2>
        <p class="muted">
          Records that failed validation are kept here verbatim and never used in calculations.
        </p>
        <p>
          @for (kv of r.issues_by_rule | keyvalue; track kv.key) {
            <span class="tag">{{ kv.key }}: {{ kv.value }}</span>
          } @empty {
            <span class="muted">No issues.</span>
          }
        </p>
        <table class="data">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Rule</th>
              <th>Message</th>
              <th>Raw record</th>
            </tr>
          </thead>
          <tbody>
            @for (i of r.recent_issues; track i.id) {
              <tr>
                <td>{{ i.dataset }}</td>
                <td>{{ i.rule }}</td>
                <td>{{ i.message }}</td>
                <td>
                  <code class="raw">{{ i.raw_record | json }}</code>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </section>

      <section class="panel">
        <h2>Model registry</h2>
        <p class="muted">
          No models registered. The first model (M2) appears here with its version, dataset
          snapshot, evaluation results and approval status.
        </p>
      </section>
    } @else {
      <p class="muted" aria-live="polite">Loading…</p>
    }
  `,
})
export class DataQuality {
  private readonly api = inject(ApiService);
  protected readonly report = signal<DataQualityReport | null>(null);
  protected readonly error = signal<ApiErrorBody | null>(null);

  constructor() {
    this.api.dataQuality().subscribe({
      next: (r) => this.report.set(r),
      error: (e: ApiErrorBody) => this.error.set(e),
    });
  }
}
