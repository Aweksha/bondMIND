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

  it('labels the environment as synthetic demo data', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.env-badge')?.textContent).toContain('SYNTHETIC DATA');
    expect(el.textContent).toContain('Not investment advice');
  });

  it('renders the spec navigation', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const labels = [...(fixture.nativeElement as HTMLElement).querySelectorAll('nav a')].map((a) =>
      a.textContent?.trim(),
    );
    expect(labels.some((l) => l?.startsWith('Screener'))).toBe(true);
    expect(labels.some((l) => l?.startsWith('Portfolio Lab'))).toBe(true);
  });
});
