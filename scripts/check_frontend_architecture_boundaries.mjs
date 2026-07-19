import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const SRC_ROOT = 'apps/frontend/src';

const violations = [];

const walk = (dir) => {
  const entries = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      entries.push(...walk(path));
    } else if (/\.(ts|tsx)$/.test(path) && !/\.(test|spec)\.(ts|tsx)$/.test(path)) {
      entries.push(path);
    }
  }
  return entries;
};

const read = (path) => readFileSync(path, 'utf8');
const rel = (path) => relative(process.cwd(), path);

const assertNoPattern = (paths, pattern, message) => {
  for (const path of paths) {
    const text = read(path);
    if (pattern.test(text)) {
      violations.push(`${rel(path)}: ${message}`);
    }
  }
};

const pages = walk(join(SRC_ROOT, 'pages'));
assertNoPattern(
  pages,
  /from ['"][^'"]*(?:lib\/fetcher|shared\/api\/fetchJson)['"]|fetchJson\s*<|fetch\s*\(/,
  'pages must not use API transport directly',
);

const featureFiles = walk(join(SRC_ROOT, 'features'));
const featureDomain = featureFiles.filter((path) => path.includes('/domain/'));
const featureApplication = featureFiles.filter((path) => path.includes('/application/'));
const featurePresentation = featureFiles.filter((path) => path.includes('/presentation/'));

assertNoPattern(
  featureDomain,
  /from ['"]react['"]|from ['"][^'"]*(?:lib\/fetcher|shared\/api\/fetchJson)['"]|fetch\s*\(/,
  'feature domain must not depend on React or API transport',
);
assertNoPattern(
  featureApplication,
  /from ['"][^'"]*(?:components|presentation)[^'"]*['"]|from ['"][^'"]*(?:lib\/fetcher|shared\/api\/fetchJson)['"]|fetch\s*\(/,
  'feature application must not depend on presentation or API transport',
);
assertNoPattern(
  featurePresentation,
  /from ['"][^'"]*(?:lib\/fetcher|shared\/api\/fetchJson)['"]|fetchJson\s*<|fetch\s*\(|\/api\//,
  'feature presentation must not use API transport or endpoint strings directly',
);

const legacyFetcherImports = featureFiles.filter((path) => {
  const text = read(path);
  return /from ['"][^'"]*lib\/fetcher['"]/.test(text);
});
for (const path of legacyFetcherImports) {
  violations.push(`${rel(path)}: feature code must import shared/api transport, not legacy lib/fetcher`);
}

if (violations.length > 0) {
  console.error('Frontend architecture boundary violations:');
  for (const violation of violations) {
    console.error(`- ${violation}`);
  }
  process.exit(1);
}

console.log('Frontend architecture boundary checks passed.');
