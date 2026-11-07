import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

import {
  ApiErrorBody,
  CurveDates,
  CurveObservations,
  DataQualityReport,
  MarketOverview,
  Page,
  ScenarioRequest,
  ScenarioResponse,
  SecurityAnalytics,
  SecurityDetail,
  SecurityFilters,
  SecurityHistory,
  SecuritySummary,
} from './api.models';

const V1 = '/api/v1';
const V2 = '/api/v2';

export function toParams(filters: object): HttpParams {
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

  private get<T>(url: string, params?: object) {
    return this.http
      .get<T>(url, { params: params ? toParams(params) : undefined })
      .pipe(catchError(toApiError));
  }

  overview(currency = 'USD') {
    return this.get<MarketOverview>(`${V1}/market/overview`, { currency });
  }

  securities(filters: SecurityFilters) {
    return this.get<Page<SecuritySummary>>(`${V1}/securities`, filters);
  }

  security(id: string) {
    return this.get<SecurityDetail>(`${V1}/securities/${encodeURIComponent(id)}`);
  }

  dataQuality() {
    return this.get<DataQualityReport>(`${V1}/data-quality`);
  }

  analytics(id: string, asOf?: string) {
    return this.get<SecurityAnalytics>(`${V2}/securities/${encodeURIComponent(id)}/analytics`, {
      asOf,
    });
  }

  history(id: string, from?: string) {
    return this.get<SecurityHistory>(`${V2}/securities/${encodeURIComponent(id)}/history`, {
      from,
    });
  }

  curveDates(curveId: string) {
    return this.get<CurveDates>(`${V2}/curves/${encodeURIComponent(curveId)}/dates`);
  }

  observations(curveId: string, dates: string[], tenors?: number[]) {
    return this.get<CurveObservations>(`${V2}/curves/${encodeURIComponent(curveId)}/observations`, {
      dates,
      tenors,
    });
  }

  evaluate(req: ScenarioRequest) {
    return this.http
      .post<ScenarioResponse>(`${V2}/scenarios/evaluate`, req)
      .pipe(catchError(toApiError));
  }
}
