"""
Interactive HTML Reader Composer.
Generates responsive, standalone Persian/English bilingual and monolingual reading pages
with Vazirmatn typography, dark/light themes, and clipboard integration.
"""
from __future__ import annotations

import html
import math
import re
from typing import Any, List, Optional, Union

from tarjoman.composers.base import BaseComposer


class HtmlReaderComposer(BaseComposer):
    """
    Composes interactive HTML readers with Vazirmatn CDN, dark/light mode,
    and instant switching between side-by-side comparative and pure Persian reading.
    """

    DEFAULT_TITLE = "خوانش تطبیقی ترجمان (Tarjoman Reader)"

    def compose(
        self,
        source_text: Union[str, List[str]],
        target_text: Union[str, List[str]],
        title: str = DEFAULT_TITLE,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """
        Generate standalone HTML reader page.

        Args:
            source_text: Source English text or list of paragraphs.
            target_text: Target Persian text or list of paragraphs.
            title: Document title shown in header and metadata.

        Returns:
            Complete HTML document string.
        """
        if isinstance(source_text, str):
            src_paras = self.split_paragraphs(source_text)
        else:
            src_paras = [p.strip() for p in source_text if p.strip()]

        if isinstance(target_text, str):
            tgt_paras = self.split_paragraphs(target_text)
        else:
            tgt_paras = [p.strip() for p in target_text if p.strip()]

        total_paragraphs = max(len(src_paras), len(tgt_paras))

        # Calculate estimated reading time (~180 Persian words/min)
        total_target_words = sum(len(p.split()) for p in tgt_paras)
        reading_time_min = max(1, math.ceil(total_target_words / 180)) if total_target_words else 1

        escaped_title = html.escape(title.strip() if title else self.DEFAULT_TITLE)

        # Build paragraph cards
        cards_html: List[str] = []
        for i in range(total_paragraphs):
            src_text = src_paras[i] if i < len(src_paras) else ""
            tgt_text = tgt_paras[i] if i < len(tgt_paras) else ""

            escaped_src = html.escape(src_text).replace("\n", "<br>")
            escaped_tgt = html.escape(tgt_text).replace("\n", "<br>")

            card = f"""      <article class="segment-card" id="seg-{i+1}">
        <div class="segment-toolbar">
          <span class="segment-badge">بند #{i+1}</span>
          <button class="btn-copy-seg" onclick="copySegment({i+1})" title="کپی ترجمه این بند">📋 کپی</button>
        </div>
        <div class="segment-content">
          <div class="source-pane" dir="ltr" lang="en">
            <p class="source-para">{escaped_src}</p>
          </div>
          <div class="target-pane" dir="rtl" lang="fa">
            <p class="target-para" id="target-text-{i+1}">{escaped_tgt}</p>
          </div>
        </div>
      </article>"""
            cards_html.append(card)

        cards_body = "\n".join(cards_html)

        # Full HTML template
        # ponytail: inline styles and minimal vanilla JS for zero build steps and offline resiliency
        return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl" data-theme="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title}</title>
  <!-- Vazirmatn Font from CDN -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;500;700;800&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css" rel="stylesheet" type="text/css" />
  <style>
    :root {{
      --bg-body: #f8fafc;
      --bg-card: #ffffff;
      --bg-source: #f1f5f9;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --text-source: #334155;
      --border: #e2e8f0;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --accent-bg: #eff6ff;
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      --radius: 12px;
    }}
    [data-theme="dark"] {{
      --bg-body: #090d16;
      --bg-card: #131b2e;
      --bg-source: #1c2640;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-source: #cbd5e1;
      --border: #273552;
      --accent: #38bdf8;
      --accent-hover: #7dd3fc;
      --accent-bg: #0c2742;
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body {{
      font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background-color: var(--bg-body);
      color: var(--text-main);
      line-height: 1.8;
      transition: background-color 0.25s, color 0.25s;
      min-height: 100vh;
      padding-bottom: 4rem;
    }}
    .header {{
      background: var(--bg-card);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      backdrop-filter: blur(10px);
      padding: 1rem 1.5rem;
      box-shadow: var(--shadow);
    }}
    .header-inner {{
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }}
    .header-info h1 {{
      font-size: 1.35rem;
      font-weight: 800;
      color: var(--text-main);
      margin-bottom: 0.25rem;
    }}
    .header-meta {{
      display: flex;
      gap: 0.75rem;
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .meta-item {{
      background: var(--accent-bg);
      color: var(--accent);
      padding: 0.2rem 0.6rem;
      border-radius: 6px;
      font-weight: 500;
    }}
    .controls {{
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }}
    .btn {{
      font-family: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      padding: 0.5rem 0.9rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--bg-card);
      color: var(--text-main);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s;
    }}
    .btn:hover {{
      border-color: var(--accent);
      color: var(--accent);
    }}
    .btn-primary {{
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }}
    .btn-primary:hover {{
      background: var(--accent-hover);
      color: #ffffff;
    }}
    .main-container {{
      max-width: 1200px;
      margin: 2rem auto;
      padding: 0 1.5rem;
    }}
    /* Bilingual Layout */
    .mode-bilingual .segment-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      margin-bottom: 1.25rem;
      padding: 1.25rem;
      box-shadow: var(--shadow);
    }}
    .mode-bilingual .segment-toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px dashed var(--border);
    }}
    .mode-bilingual .segment-badge {{
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--text-muted);
    }}
    .mode-bilingual .btn-copy-seg {{
      background: transparent;
      border: none;
      font-family: inherit;
      font-size: 0.8rem;
      color: var(--text-muted);
      cursor: pointer;
    }}
    .mode-bilingual .btn-copy-seg:hover {{
      color: var(--accent);
    }}
    .mode-bilingual .segment-content {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
    }}
    .mode-bilingual .source-pane {{
      background: var(--bg-source);
      padding: 1rem 1.25rem;
      border-radius: 8px;
      font-family: system-ui, -apple-system, sans-serif;
      font-size: 0.95rem;
      color: var(--text-source);
      line-height: 1.7;
    }}
    .mode-bilingual .target-pane {{
      padding: 0.5rem 0.25rem;
      font-size: 1.05rem;
      line-height: 2.1;
      text-align: justify;
    }}
    /* Pure Persian Reading Mode */
    .mode-persian {{
      max-width: 780px;
      margin: 2rem auto;
    }}
    .mode-persian .segment-card {{
      background: transparent;
      border: none;
      box-shadow: none;
      margin-bottom: 1.25rem;
      padding: 0;
    }}
    .mode-persian .segment-toolbar {{
      display: none;
    }}
    .mode-persian .source-pane {{
      display: none;
    }}
    .mode-persian .segment-content {{
      display: block;
    }}
    .mode-persian .target-pane {{
      font-size: 1.18rem;
      line-height: 2.3;
      text-align: justify;
      text-indent: 1.8rem;
      color: var(--text-main);
    }}
    /* Toast Notification */
    .toast {{
      position: fixed;
      bottom: 2rem;
      left: 50%;
      transform: translateX(-50%) translateY(100px);
      background: #10b981;
      color: #ffffff;
      padding: 0.6rem 1.2rem;
      border-radius: 8px;
      font-size: 0.9rem;
      font-weight: 600;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2);
      opacity: 0;
      transition: all 0.3s ease;
      z-index: 1000;
    }}
    .toast.show {{
      transform: translateX(-50%) translateY(0);
      opacity: 1;
    }}
    @media (max-width: 768px) {{
      .mode-bilingual .segment-content {{
        grid-template-columns: 1fr;
        gap: 1rem;
      }}
      .header-inner {{
        flex-direction: column;
        align-items: flex-start;
      }}
    }}
  </style>
</head>
<body>
  <header class="header">
    <div class="header-inner">
      <div class="header-info">
        <h1>{escaped_title}</h1>
        <div class="header-meta">
          <span class="meta-item">تعداد بندها: {total_paragraphs}</span>
          <span class="meta-item">زمان تقریبی مطالعه: {reading_time_min} دقیقه</span>
        </div>
      </div>
      <div class="controls">
        <button id="themeToggleBtn" class="btn" onclick="toggleTheme()" title="تغییر تم رنگی">
          <span id="themeIcon">🌙</span> <span id="themeLabel">حالت شب</span>
        </button>
        <button id="modeToggleBtn" class="btn" onclick="toggleViewMode()" title="تغییر سبک نمایش">
          <span id="modeIcon">📖</span> <span id="modeLabel">مطالعه فارسی</span>
        </button>
        <button id="copyAllBtn" class="btn btn-primary" onclick="copyFullTranslation()" title="کپی کل ترجمه فارسی">
          📋 کپی کل متن
        </button>
      </div>
    </div>
  </header>

  <main id="readerContainer" class="main-container mode-bilingual">
{cards_body}
  </main>

  <div id="toast" class="toast">کپی شد!</div>

  <script>
    // Theme toggle logic
    function toggleTheme() {{
      const html = document.documentElement;
      const current = html.getAttribute('data-theme') || 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      document.getElementById('themeLabel').textContent = next === 'dark' ? 'حالت روز' : 'حالت شب';
      document.getElementById('themeIcon').textContent = next === 'dark' ? '☀️' : '🌙';
    }}

    // View mode toggle logic: bilingual comparative vs pure Persian reading
    function toggleViewMode() {{
      const container = document.getElementById('readerContainer');
      const isBilingual = container.classList.contains('mode-bilingual');
      if (isBilingual) {{
        container.classList.remove('mode-bilingual');
        container.classList.add('mode-persian');
        document.getElementById('modeLabel').textContent = 'نمای تطبیقی دوزبانه';
        document.getElementById('modeIcon').textContent = '⚖️';
      }} else {{
        container.classList.remove('mode-persian');
        container.classList.add('mode-bilingual');
        document.getElementById('modeLabel').textContent = 'مطالعه فارسی';
        document.getElementById('modeIcon').textContent = '📖';
      }}
    }}

    // Clipboard copy helpers
    function showToast(msg) {{
      const toast = document.getElementById('toast');
      toast.textContent = msg;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2000);
    }}

    function copySegment(segNum) {{
      const elem = document.getElementById('target-text-' + segNum);
      if (elem) {{
        navigator.clipboard.writeText(elem.innerText || elem.textContent).then(() => {{
          showToast('بند #' + segNum + ' کپی شد!');
        }});
      }}
    }}

    function copyFullTranslation() {{
      const paras = document.querySelectorAll('.target-para');
      const fullText = Array.from(paras).map(p => p.innerText || p.textContent).join('\\n\\n');
      navigator.clipboard.writeText(fullText).then(() => {{
        showToast('کل متن ترجمه کپی شد!');
      }});
    }}
  </script>
</body>
</html>"""
