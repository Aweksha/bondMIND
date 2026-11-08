import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { App } from './app';

describe('App shell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([]), provideHttpClient()],
    }).compileComponents();
  });

  it('labels synthetic and real data sources and the disclaimer', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('synthetic');
    expect(text).toContain('real');
    expect(text).toContain('Not investment advice');
  });

  it('has exactly the three feature tabs', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const labels = [...(fixture.nativeElement as HTMLElement).querySelectorAll('.tabs a')].map(
      (a) => a.textContent?.trim(),
    );
    expect(labels).toEqual(['Bond Explorer', 'Yield Curve', 'Price Simulator']);
  });
});
