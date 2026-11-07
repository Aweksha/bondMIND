import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiErrorBody } from './api.models';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  it('serialises repeated filter params and skips empty values', () => {
    api.securities({ rating: ['A', 'BBB'], q: '', min_yield: null, page: 2 }).subscribe();
    const req = http.expectOne((r) => r.url === '/api/v1/securities');
    expect(req.request.params.getAll('rating')).toEqual(['A', 'BBB']);
    expect(req.request.params.has('q')).toBe(false);
    expect(req.request.params.has('min_yield')).toBe(false);
    expect(req.request.params.get('page')).toBe('2');
    req.flush({ items: [], total: 0, page: 2, page_size: 50, context: {} });
  });

  it('maps API errors to the error contract', () => {
    let err: ApiErrorBody | undefined;
    api.security('X').subscribe({ error: (e) => (err = e) });
    http
      .expectOne('/api/v1/securities/X')
      .flush(
        { code: 'not_found', message: 'security X not found', details: null, request_id: 'r1' },
        { status: 404, statusText: 'Not Found' },
      );
    expect(err).toEqual({
      code: 'not_found',
      message: 'security X not found',
      details: null,
      request_id: 'r1',
    });
  });
});
