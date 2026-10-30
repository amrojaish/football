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

  /* (30 أكتوبر 2026، دفعة 3 بند 1) خانة البحث المشتركة بكل الموقع (search_field): كبسولة FotMob، عدسة 20px بجهة البداية
     (يسار بالإنجليزي، يمين بالعربي) والنص بعدها. صفحة البحث، الدوريات، ورقة «+» بالمتابَعة. */
  .sfield { position:relative; display:block; width:100%; }
  .sfield input { width:100%; background:var(--card); color:var(--text); border:1px solid var(--line); border-radius:999px;
                  padding:12px 16px; padding-inline-start:46px; min-height:46px; font-size:16px; font-family:inherit;
                  -webkit-appearance:none; appearance:none; }
  .sfield input:focus { outline:none; border-color:var(--accent); }
  .sfield input::-webkit-search-decoration, .sfield input::-webkit-search-cancel-button { -webkit-appearance:none; }
  .sfield .sico { position:absolute; top:50%; inset-inline-start:16px; transform:translateY(-50%); width:20px; height:20px;
                  display:flex; color:var(--muted); pointer-events:none; }
  .sfield .sico svg { width:20px; height:20px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; }
  #lgsearch.sfield { max-width:520px; margin:0 auto 22px; }   /* صفحة الدوريات */
  .appname.lgbig { font-size:clamp(28px,8.6vw,34px); font-weight:800; letter-spacing:-.3px; }

  .sempty { color:var(--muted); font-size:14px; text-align:center;
            padding:26px 10px; }
"""

SEARCH_ICON = ('<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
               '<path d="M20 20l-3.6-3.6"/></svg>')


def search_field(input_html, cls="", wrap_id=""):
    """خانة البحث المشتركة (30 أكتوبر 2026): <div class="sfield"> + العدسة بجهة البداية + الحقل كما يمرّره المستدعي (معرّفه وسماته)"""
    wid = f' id="{wrap_id}"' if wrap_id else ""
    return f'<div class="sfield{(" " + cls) if cls else ""}"{wid}><span class="sico">{SEARCH_ICON}</span>{input_html}</div>'
