import { Observable, OperatorFunction, catchError, map, of, startWith } from 'rxjs';

import { ApiErrorBody } from './api.models';

export type Load<T> =
  { state: 'loading' } | { state: 'ok'; data: T } | { state: 'error'; error: ApiErrorBody };

/** Wraps a request so panels can render loading / data / error without blanking others. */
export function load<T>(): OperatorFunction<T, Load<T>> {
  return (source: Observable<T>) =>
    source.pipe(
      map((data) => ({ state: 'ok', data }) as Load<T>),
      catchError((error: ApiErrorBody) => of({ state: 'error', error } as Load<T>)),
      startWith({ state: 'loading' } as Load<T>),
    );
}
