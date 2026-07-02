module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 's-maxage=86400, stale-while-revalidate=604800');
  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  const apiKey = process.env.KOSIS_API_KEY || process.env.KOSIS_PUBLIC_API_KEY;
  const userStatsId = process.env.KOSIS_TREND_USER_STATS_ID;

  if (!apiKey || !userStatsId) {
    res.statusCode = 503;
    res.end(JSON.stringify({
      ok: false,
      error: 'KOSIS_API_KEY and KOSIS_TREND_USER_STATS_ID are required on the deployment.'
    }));
    return;
  }

  const params = new URLSearchParams({
    method: 'getList',
    apiKey,
    format: 'json',
    jsonVD: 'Y',
    userStatsId,
    prdSe: 'Y',
    startPrdDe: req.query?.start || '1925',
    endPrdDe: req.query?.end || '2070'
  });

  try {
    const upstream = await fetch(`https://kosis.kr/openapi/statisticsData.do?${params.toString()}`, {
      headers: { Accept: 'application/json' }
    });
    const text = await upstream.text();
    res.statusCode = upstream.ok ? 200 : upstream.status;
    res.end(text);
  } catch (error) {
    res.statusCode = 502;
    res.end(JSON.stringify({ ok: false, error: 'KOSIS upstream request failed' }));
  }
};
