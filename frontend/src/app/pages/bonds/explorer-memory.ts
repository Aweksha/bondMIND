import { Injectable, signal } from '@angular/core';
import { Params } from '@angular/router';

/** Remembers the explorer filters so "Back to explorer" returns to the same view. */
@Injectable({ providedIn: 'root' })
export class ExplorerMemory {
  readonly lastQuery = signal<Params>({});
}
