import {
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import { BarChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  DataZoomComponent,
  MarkLineComponent,
  TitleComponent,
  AriaComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;

function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Applies app colour tokens so charts follow light/dark mode. */
function themed(option: ChartOption): ChartOption {
  const text = token('--text');
  const muted = token('--text-muted');
  const border = token('--border');
  const axis = {
    axisLine: { lineStyle: { color: border } },
    axisLabel: { color: muted },
    splitLine: { lineStyle: { color: border, opacity: 0.5 } },
    nameTextStyle: { color: muted },
  };
  const merge = (a: unknown) =>
    Array.isArray(a) ? a.map((x) => ({ ...axis, ...x })) : a ? { ...axis, ...(a as object) } : a;
  return {
    backgroundColor: 'transparent',
    textStyle: { color: text, fontFamily: token('--font-ui') },
    color: ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5'].map(token),
    aria: { enabled: true },
    animationDuration: 200,
    ...option,
    legend: option['legend'] ? { textStyle: { color: muted }, ...option['legend'] } : undefined,
    tooltip: {
      backgroundColor: token('--surface-2'),
      borderColor: border,
      textStyle: { color: text },
      ...(option['tooltip'] as object),
    },
    xAxis: merge(option['xAxis']),
    yAxis: merge(option['yAxis']),
  };
}

@Component({
  selector: 'bm-chart',
  template: `
    <div class="chart-head">
      <span class="chart-title">{{ title() }}</span>
      <button
        type="button"
        class="ghost"
        (click)="exportPng()"
        [attr.aria-label]="'Export ' + title() + ' as PNG'"
      >
        PNG
      </button>
    </div>
    <div
      #host
      class="chart"
      role="img"
      [attr.aria-label]="ariaLabel()"
      [style.height.px]="height()"
    ></div>
  `,
})
export class Chart {
  readonly option = input.required<ChartOption>();
  readonly title = input('');
  readonly ariaLabel = input('Chart. See the table below for the same data.');
  readonly height = input(280);
  readonly filename = input('bondmind-chart');

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private chart?: echarts.ECharts;

  constructor() {
    const destroyRef = inject(DestroyRef);
    afterNextRender(() => {
      this.chart = echarts.init(this.host().nativeElement);
      this.chart.setOption(themed(this.option()), true);
      const ro = new ResizeObserver(() => this.chart?.resize());
      ro.observe(this.host().nativeElement);
      const scheme = matchMedia('(prefers-color-scheme: dark)');
      const retheme = () => this.chart?.setOption(themed(this.option()), true);
      scheme.addEventListener('change', retheme);
      destroyRef.onDestroy(() => {
        ro.disconnect();
        scheme.removeEventListener('change', retheme);
        this.chart?.dispose();
      });
    });
    effect(() => {
      const opt = this.option();
      this.chart?.setOption(themed(opt), true);
    });
  }

  exportPng(): void {
    if (!this.chart) return;
    const url = this.chart.getDataURL({
      type: 'png',
      pixelRatio: 2,
      backgroundColor: token('--surface'),
    });
    const a = Object.assign(document.createElement('a'), {
      href: url,
      download: `${this.filename()}.png`,
    });
    a.click();
  }
}
