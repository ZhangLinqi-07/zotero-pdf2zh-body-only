/* SPDX-License-Identifier: AGPL-3.0-only
 * Renderer regression test. Native Zotero integration separately verifies sanitization and saving. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const scope = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(root, 'payload/web/vendor/marked.js'), 'utf8'), scope);
vm.runInContext(fs.readFileSync(path.join(root, 'plugin/reading_note.js'), 'utf8'), scope);
const job = { id: 'b'.repeat(32), documentId: 'c'.repeat(32), state: 'completed', filename: 'paper.pdf',
  zoteroTarget: { title: 'Evidence <and> assumptions' },
  markdown: '# Findings\n\nInline $x_i^2$ and $a<b$ remain editable.\n\n$$E=mc^2$$\n\n$$\\sum_i x_i = $&$$' };
const html = scope.BodyOnlyNotes.render(job, 'http://127.0.0.1:8891', scope.marked, { sanitize: value => value });
assert(html.includes('<span class="math">$x_i^2$</span>'));
assert(html.includes('<span class="math">$a&lt;b$</span>'));
assert(html.includes('<pre class="math">$$E=mc^2$$</pre>'));
assert(html.includes('<pre class="math">$$\\sum_i x_i = $&amp;$$</pre>'));
assert(html.includes('Evidence &lt;and&gt; assumptions'));
assert(html.includes('readingJob=' + job.id));
assert(!html.includes('PDF2ZHNATIVEMATH'));
job.state = 'partial';
assert(scope.BodyOnlyNotes.render(job, 'http://127.0.0.1:8891', scope.marked, { sanitize: value => value }).includes('未完成的深度阅读'));
console.log('Native-note formatting regression passed');
