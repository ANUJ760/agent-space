import { Server } from '@hocuspocus/server';
import * as Y from 'yjs';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, realpathSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { resolve, relative, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(process.env.WORKSPACE_ROOT || join(dirname(fileURLToPath(import.meta.url)), '../../var/workspaces'));
const api = process.env.COLLAB_API_URL || 'http://127.0.0.1:8000';
const port = Number(process.env.COLLAB_PORT || 1234);
const savedContent = new Map();

function paths(documentName) {
  const slash = documentName.indexOf('/');
  const projectId = documentName.slice(0, slash);
  let filename;
  try { filename = decodeURIComponent(documentName.slice(slash + 1)); } catch { throw new Error('Invalid file name'); }
  if (!/^[0-9a-f]{8}-[0-9a-f-]{27,}$/.test(projectId) ||
      !filename || filename.length > 240 || filename.includes('\\') || filename.includes('\0') ||
      filename.split('/').some(part => !part || part.startsWith('.') || part === '..')) {
    throw new Error('Invalid document name');
  }
  const projectRoot = join(root, projectId);
  const file = resolve(projectRoot, filename);
  if (relative(projectRoot, file).startsWith('..')) throw new Error('Invalid file path');
  if (existsSync(file) && relative(projectRoot, realpathSync(file)).startsWith('..')) throw new Error('Invalid file path');
  const yjs = join(projectRoot, '.yjs', createHash('sha256').update(filename).digest('hex'));
  return { projectId, file, yjs };
}

function atomicWrite(path, data) {
  mkdirSync(dirname(path), { recursive: true });
  const temp = `${path}.${process.pid}.${Math.random().toString(36).slice(2)}.tmp`;
  writeFileSync(temp, data, { mode: 0o600 });
  renameSync(temp, path);
}

const server = new Server({
  port,
  debounce: 1000,
  maxDebounce: 5000,
  async onAuthenticate({ documentName, token }) {
    const { projectId, file } = paths(documentName);
    if (!token) throw new Error('Project access denied');
    const response = await fetch(`${api}/api/v1/projects/${projectId}/workspace/access`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) throw new Error('Project access denied');
    if (!existsSync(file)) throw new Error('File not found');
    return { token, checkedAt: Date.now() };
  },
  async beforeHandleMessage({ documentName, context }) {
    if (!context?.token) throw new Error('Project access denied');
    if (Date.now() - context.checkedAt > 60000) {
      const { projectId } = paths(documentName);
      const response = await fetch(`${api}/api/v1/projects/${projectId}/workspace/access`, {
        headers: { Authorization: `Bearer ${context.token}` },
        signal: AbortSignal.timeout(5000),
      });
      if (!response.ok) throw new Error('Project access expired');
      context.checkedAt = Date.now();
    }
  },
  async onLoadDocument({ documentName }) {
    const { file, yjs } = paths(documentName);
    if (!existsSync(file)) throw new Error('File not found');
    const doc = new Y.Doc();
    if (existsSync(yjs)) {
      Y.applyUpdate(doc, readFileSync(yjs));
      const restored = doc.getText('content').toString();
      const disk = readFileSync(file, 'utf8');
      if (restored !== disk) {
        if (statSync(file).mtimeMs > statSync(yjs).mtimeMs) {
          doc.transact(() => { doc.getText('content').delete(0, doc.getText('content').length); doc.getText('content').insert(0, disk); });
          atomicWrite(yjs, Y.encodeStateAsUpdate(doc));
        } else {
          atomicWrite(file, restored);
        }
      }
    } else {
      doc.getText('content').insert(0, readFileSync(file, 'utf8'));
    }
    savedContent.set(documentName, doc.getText('content').toString());
    return doc;
  },
  async onStoreDocument({ documentName, document }) {
    const { file, yjs } = paths(documentName);
    if (!existsSync(file)) return;
    const content = document.getText('content').toString();
    if (Buffer.byteLength(content, 'utf8') > 1024 * 1024) throw new Error('File exceeds 1 MB limit');
    atomicWrite(yjs, Y.encodeStateAsUpdate(document));
    atomicWrite(file, content);
    savedContent.set(documentName, content);
  },
  afterUnloadDocument({ documentName }) { savedContent.delete(documentName); },
});

server.listen();
setInterval(() => {
  for (const [name, doc] of server.hocuspocus.documents) {
    try {
      const { file } = paths(name);
      if (!existsSync(file) || statSync(file).size > 1024 * 1024) continue;
      const last = savedContent.get(name);
      if (last === undefined || doc.getText('content').toString() !== last) continue;
      const disk = readFileSync(file, 'utf8');
      if (disk === last) continue;
      savedContent.set(name, disk);
      doc.transact(() => {
        doc.getText('content').delete(0, doc.getText('content').length);
        doc.getText('content').insert(0, disk);
      });
    } catch (error) { console.error('Could not import external workspace edit:', error); }
  }
}, 2000).unref();
console.log(`Collaboration server listening on ${port}`);
