import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const VERSION = process.env.ADK_BOUNDARY_VERSION || '20251231';
const BASE_URL = process.env.ADK_BOUNDARY_BASE_URL || 'https://raw.githubusercontent.com/vuski/admdongkor/master/parquet/simplified';
const OUT_DIR = process.env.ADK_BOUNDARY_OUT_DIR || 'data/boundaries';
const LEVELS = ['sido', 'sgg', 'emd'];

async function importDependency(name, fallbackEntry) {
  try {
    return await import(name);
  } catch (error) {
    const modulesDir = process.env.ADK_EXPORT_NODE_MODULES;
    if (!modulesDir) throw error;
    const packagePath = path.join(modulesDir, name, 'package.json');
    await readFile(packagePath, 'utf8');
    return import(pathToFileURL(path.join(modulesDir, name, fallbackEntry)).href);
  }
}

const { parquetReadObjects } = await importDependency('hyparquet', 'src/node.js');
const { compressors } = await importDependency('hyparquet-compressors', 'src/index.js');

await mkdir(OUT_DIR, { recursive: true });

const manifest = {
  version: VERSION,
  source: 'admdongkor',
  sourceUrl: BASE_URL,
  files: {},
  note: 'Local administrative boundary GeoJSON files used by pyramid.html before falling back to the CDN.',
};

for (const level of LEVELS) {
  const url = `${BASE_URL}/${level}_${VERSION}_light.parquet`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }
  const rows = await parquetReadObjects({
    file: await response.arrayBuffer(),
    compressors,
  });
  const featureCollection = {
    type: 'FeatureCollection',
    features: rows.map(({ geometry, ...properties }) => ({
      type: 'Feature',
      properties,
      geometry,
    })),
  };
  const filename = `${level}_${VERSION}_light.geojson`;
  const filepath = path.join(OUT_DIR, filename);
  await writeFile(filepath, JSON.stringify(featureCollection));
  manifest.files[level] = {
    filename,
    featureCount: featureCollection.features.length,
    sourceParquet: `${level}_${VERSION}_light.parquet`,
  };
  console.log(`${filename}: ${featureCollection.features.length.toLocaleString()} features`);
}

await writeFile(path.join(OUT_DIR, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
