export function escapeHtml(value: unknown): string {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function inline(text: string): string {
  return text
    .replaceAll(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replaceAll(/`([^`]+)`/g, "<code>$1</code>");
}

export function renderMarkdown(src: string): string {
  const escaped = escapeHtml(src || "");
  const blocks = escaped.split(/```(?:\w*)\n?/);
  const html = blocks
    .map((chunk, index) => {
      if (index % 2 === 1) {
        return `<pre><code>${chunk.replace(/\n$/, "")}</code></pre>`;
      }
      return chunk
        .split("\n")
        .map((line) => {
          if (line.startsWith("### ")) return `<h3>${inline(line.slice(4))}</h3>`;
          if (line.startsWith("## ")) return `<h2>${inline(line.slice(3))}</h2>`;
          if (line.startsWith("# ")) return `<h1>${inline(line.slice(2))}</h1>`;
          if (line.startsWith("- ")) return `<li>${inline(line.slice(2))}</li>`;
          if (!line.trim()) return "";
          return `<p>${inline(line)}</p>`;
        })
        .join("\n")
        .replaceAll(/(?:<li>.*<\/li>\n?)+/g, (list: string) => `<ul>${list}</ul>`);
    })
    .join("");
  return html || '<p class="muted">Empty file.</p>';
}
