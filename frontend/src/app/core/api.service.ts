import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map, shareReplay, tap, throwError, catchError } from 'rxjs';

import {
  ApiErrorBody,
  BondQuery,
  DataQualityReport,
  HistoryPoint,
  PriceYield,
  SecurityAnalytics,
  SecurityDetail,
  SecurityHistory,
} from './api.models';
import { BondsFile, CurveFile, curveDates, observations, queryBonds, series } from './static-data';

/**
 * Data access for the website. All figures are pre-computed at build time by the validated
 * Python engine (backend/app/export/static_site.py) and served as static JSON next to the app,
 * so the site runs on any static host (GitHub Pages). Paths are relative to the base href.
 */
const DATA = 'data';
const SAFE_ID = /^[A-Za-z0-9-]{1,32}$/;

interface BondFile {
  security: SecurityDetail;
  analytics: SecurityAnalytics | null;
  analytics_error: { code: string; message: string } | null;
  history: SecurityHistory & { points: HistoryPoint[] };
}

function apiError(code: string, message: string): ApiErrorBody {
  return { code, message, details: null, request_id: null };
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly cache = new Map<string, Observable<unknown>>();

  /** Fetch one data file once per session; failed fetches are not cached (retry works). */
  private file<T>(path: string, notFound: string): Observable<T> {
    let obs = this.cache.get(path) as Observable<T> | undefined;
    if (!obs) {
      obs = this.http.get<T>(`${DATA}/${path}`).pipe(
        catchError((err: HttpErrorResponse) => {
          this.cache.delete(path);
          return throwError(() =>
            err.status === 404
              ? apiError('not_found', notFound)
              : apiError(
                  err.status === 0 ? 'network_error' : 'http_error',
                  err.status === 0
                    ? 'Data unreachable. Check your connection.'
                    : `Could not load data (${err.status}).`,
                ),
          );
        }),
        shareReplay(1),
      );
      this.cache.set(path, obs);
    }
    return obs;
  }

  private bondFile(id: string): Observable<BondFile> {
    if (!SAFE_ID.test(id)) return throwError(() => apiError('not_found', `Bond ${id} not found`));
    return this.file<BondFile>(`bonds/${id}.json`, `Bond ${id} not found`);
  }

  private curve(): Observable<CurveFile> {
    return this.file<CurveFile>('curve.json', 'Curve data not found');
  }

  bonds(query: BondQuery) {
    return this.file<BondsFile>('bonds.json', 'Bond list not found').pipe(
      map((f) => queryBonds(f, query)),
    );
  }

  security(id: string) {
    return this.bondFile(id).pipe(map((f) => f.security));
  }

  analytics(id: string): Observable<SecurityAnalytics> {
    return this.bondFile(id).pipe(
      tap((f) => {
        if (!f.analytics) throw f.analytics_error ?? apiError('unavailable', 'No analytics');
      }),
      map((f) => f.analytics!),
    );
  }

  history(id: string) {
    return this.bondFile(id).pipe(map((f) => f.history));
  }

  curveDates(_curveId: string) {
    return this.curve().pipe(map(curveDates));
  }

  observations(_curveId: string, dates: string[], tenors?: number[]) {
    return this.curve().pipe(map((c) => observations(c, dates, tenors)));
  }

  curveSeries(_curveId: string, tenors: number[], from?: string, to?: string) {
    return this.curve().pipe(map((c) => series(c, tenors, from, to)));
  }

  priceYield(id: string): Observable<PriceYield> {
    if (!SAFE_ID.test(id)) return throwError(() => apiError('not_found', `Bond ${id} not found`));
    return this.file<PriceYield>(
      `price-yield/${id}.json`,
      `${id} can't be simulated (unknown bond or unsupported instrument)`,
    );
  }

  dataQuality() {
    return this.file<DataQualityReport>('data-quality.json', 'Data report not found');
  }
}
