#!/usr/bin/env python3
"""
CSS البحث المشترك — `SEARCH_CSS`
==================================
بقي من هذه الوحدة قاعدتان فقط تستعملهما صفحة الدوريات: `.sbig` (صندوق البحث المحلي
`#lgsearch`) و`.sempty` (رسالة فارغة). يُضاف `SEARCH_CSS` لبلوك STYLE (وإلى
`assets/site.css` عبر `make_assets.py`).

⚠️ **حُذف 5 أكتوبر 2026 (دفعة التنظيف):** `search_box()` و`search_script()` و`search_overlay()`
   ونافذة البحث (`#sovl` + CSS). البحث صار **صفحة مستقلة** — `make_search_page.py`
   (`search.html` / `en/search.html`)، وهي وحدها التي تحمّل `search_data.js`. بادئتا الروابط
   (UP للأصول بالجذر، UPL للصفحات المترجَمة) صارتا بـ`make_search_page.page_js()`.
   المرجع التاريخي: `git log -- search_view.py`.
"""

SEARCH_CSS = """
  .sbig { width:100%; max-width:520px; margin:0 auto 22px;
          display:block; position:relative; }
  .sbig input { width:100%; background:var(--card);
          border:1px solid var(--line); border-radius:11px;
          padding:13px 44px 13px 16px; color:var(--text);
          font-size:16px; font-family:inherit; }
  .sbig input:focus { outline:none; border-color:var(--accent); }
  .sbig .ico { position:absolute; top:50%; inset-inline-end:15px;
          transform:translateY(-50%); color:var(--muted);
          font-size:15px; pointer-events:none; }

  .sempty { color:var(--muted); font-size:14px; text-align:center;
            padding:26px 10px; }
"""
