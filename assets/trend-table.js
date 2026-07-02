(function (root) {
  'use strict';

  const metricLabels = {
    total: '총인구',
    young: '유소년',
    working: '생산가능',
    senior: '고령'
  };

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    }[ch]));
  }

  function formatTrendCell(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return '-';
    return (n / 10000).toLocaleString('ko-KR', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1
    }) + '만';
  }

  function buildTrendYearRows(trend, activeMetric = 'total') {
    const years = Array.isArray(trend?.years) ? trend.years : [];
    const series = trend?.series || {};
    const cutoff = Number(trend?.cutoffYear || 2025);

    return years.map((year, i) => {
      const kind = Number(year) > cutoff ? '추계' : '관측';
      const cells = Object.keys(metricLabels).map(metric => {
        const active = metric === activeMetric ? ' active' : '';
        return `<td class="num${active}">${esc(formatTrendCell(series[metric]?.[i]))}</td>`;
      }).join('');

      return `<tr class="${kind === '추계' ? 'projected' : 'observed'}"><th scope="row" class="num">${esc(year)}</th>${cells}<td>${kind}</td></tr>`;
    }).join('');
  }

  function renderTrendYearTable(host, trend, activeMetric = 'total') {
    if (!host) return;
    const rows = buildTrendYearRows(trend, activeMetric);
    if (!rows) {
      host.innerHTML = '<div class="trend-empty">표시할 연도별 자료가 없습니다</div>';
      return;
    }

    const headerCells = Object.entries(metricLabels).map(([metric, label]) => {
      const active = metric === activeMetric ? ' class="active"' : '';
      return `<th scope="col"${active}>${esc(label)}</th>`;
    }).join('');

    host.innerHTML = `<div class="trend-table-scroll">
      <table class="trend-year-grid">
        <thead><tr><th scope="col">연도</th>${headerCells}<th scope="col">구분</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  const api = { buildTrendYearRows, renderTrendYearTable, formatTrendCell };
  root.TrendYearTable = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : globalThis);
