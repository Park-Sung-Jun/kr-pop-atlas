const assert = require('node:assert/strict');
const test = require('node:test');

const { buildTrendYearRows } = require('../assets/trend-table.js');

test('buildTrendYearRows renders every year with all population metrics', () => {
  const rows = buildTrendYearRows({
    years: [1925, 1926, 2070],
    series: {
      total: [19020000, 19100000, 37000000],
      young: [6500000, 6510000, 3800000],
      working: [11800000, 11890000, 18000000],
      senior: [720000, 730000, 15200000]
    }
  });

  assert.equal((rows.match(/<tr/g) || []).length, 3);
  assert.match(rows, /1925/);
  assert.match(rows, /2070/);
  assert.match(rows, /1,902\.0만/);
  assert.match(rows, /380\.0만/);
  assert.match(rows, /추계/);
});
