import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import {
  ApiErrorBody,
  DataQualityReport,
  MarketOverview,
  Page,
  SecurityDetail,
  SecurityFilters,
  SecuritySummary,
} from './api.models';

const BASE = '/api/v1';

function toParams(filters: object): HttpParams {
  let params = new HttpParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value === undefined || value === null || value === '') continue;
    for (const v of Array.isArray(value) ? value : [value]) params = params.append(key, String(v));
  }
  return params;
}

/** Normalises transport and API errors into the backend's {code, message, request_id} shape. */
function toApiError(err: HttpErrorResponse): Observable<never> {
  const body = err.error as Partial<ApiErrorBody> | null;
  return throwError(
    () =>
      ({
        code: body?.code ?? (err.status === 0 ? 'network_error' : 'http_error'),
        message: body?.message ?? (err.status === 0 ? 'API unreachable' : err.message),
        details: body?.details ?? null,
        request_id: body?.request_id ?? null,
      }) satisfies ApiErrorBody,
  );
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);

  overview(currency = 'USD') {
    return this.http
      .get<MarketOverview>(`${BASE}/market/overview`, { params: { currency } })
      .pipe(catchError(toApiError));
  }

  securities(filters: SecurityFilters) {
    return this.http
      .get<Page<SecuritySummary>>(`${BASE}/securities`, { params: toParams(filters) })
      .pipe(catchError(toApiError));
  }

  security(id: string) {
    return this.http
      .get<SecurityDetail>(`${BASE}/securities/${encodeURIComponent(id)}`)
      .pipe(catchError(toApiError));
  }

  dataQuality() {
    return this.http.get<DataQualityReport>(`${BASE}/data-quality`).pipe(catchError(toApiError));
  }
}
