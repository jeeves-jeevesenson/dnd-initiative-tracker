import { spawnSync } from 'node:child_process';
import { readFileSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..');
const htmlPath = path.join(repoRoot, 'assets', 'web', 'lan', 'index.html');

const html = readFileSync(htmlPath, 'utf8');
const scriptRegex = /<script\b([^>]*)>([\s\S]*?)<\/script>/gi;
const inlineScripts = [];
let match;

while ((match = scriptRegex.exec(html)) !== null) {
  const attrs = match[1] ?? '';
  if (/\bsrc\s*=/.test(attrs)) {
    continue;
  }
  const content = match[2].trim();
  if (content) {
    inlineScripts.push(content);
  }
}

if (inlineScripts.length === 0) {
  console.error('No inline <script> blocks found in assets/web/lan/index.html.');
  process.exit(1);
}

const tempDir = mkdtempSync(path.join(tmpdir(), 'lan-script-'));
const tempFile = path.join(tempDir, 'lan-inline.js');
writeFileSync(tempFile, inlineScripts.join('\n\n'), 'utf8');

const result = spawnSync(process.execPath, ['--check', tempFile], { stdio: 'inherit' });
process.exit(result.status ?? 1);
