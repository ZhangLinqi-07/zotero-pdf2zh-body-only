/* SPDX-License-Identifier: AGPL-3.0-only */
var BodyOnlyNotes = (() => {
  function escape(value) {
    return String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function render(job, base, marked, purify) {
    const math = [];
    const source = String(job.markdown || '').replace(/\$\$[\s\S]*?\$\$|\$(?:\\.|[^$\\\n])+\$/g, value => {
      const token = `PDF2ZHNATIVEMATH${math.push(value) - 1}END`;
      return value.startsWith('$$') ? `\n\n${token}\n\n` : token;
    });
    const parser = new marked.Marked({ renderer: { html: () => '', image: token => escape(token.text || '') } });
    let html = purify.sanitize(parser.parse(source), {
      ALLOWED_TAGS: ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'strong', 'em', 's', 'blockquote', 'pre', 'code', 'a', 'br', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'sup', 'sub'],
      ALLOWED_ATTR: ['href', 'title'], ALLOW_DATA_ATTR: false,
    });
    math.forEach((value, index) => {
      const token = `PDF2ZHNATIVEMATH${index}END`;
      const node = value.startsWith('$$') ? `<pre class="math">${escape(value)}</pre>` : `<span class="math">${escape(value)}</span>`;
      html = html.replace(new RegExp(`<p>\\s*${token}\\s*</p>`, 'g'), () => node).replaceAll(token, () => node);
    });
    const title = (job.state === 'partial' ? '未完成的深度阅读' : '深度结构化阅读') + ' · ' + (job.zoteroTarget?.title || job.filename || '论文');
    const link = `${base}/?reading=${encodeURIComponent(job.documentId)}&readingJob=${encodeURIComponent(job.id)}#reading`;
    return `<div data-schema-version="9"><h1>${escape(title)}</h1>${html}<p><a href="${escape(link)}">查看本次阅读记录</a></p></div>`;
  }
  return { render };
})();
