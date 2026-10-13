#!/usr/bin/env python3
"""
صفحة الإشعارات — Notifications (13 أكتوبر 2026، دفعة 3E)
=========================================================
الإعدادات ← الإشعارات: تبويبان «الفرق / الدوريات». كل صف = الكيان + جرس (تشغيل/إيقاف كل الأنواع بنقرة) + رابط «تعديل» (ورقة الأنواع)
+ سطر ملخّص («كل الأنواع» أو «3 أنواع»). الدوريات: اشتراك على مستوى الدوري (كل مباريات الدوري السبعة). تحت تبويب الفرق قسم «مباريات» لما فُعِّل لمباراة
بعينها من صفحتها. كل الحالة محلية عبر المحرّك المشترك `push_ui.py` (window.FBPush) — لا خادم ولا بيانات جديدة بالصفحة نفسها: أسماء/شعارات الفرق
تُقرأ من follow_data.js (نفس ملف صفحة المتابَعة، يُحمَّل كسولاً).

⚠️ نفس بوّابة الجرس بكل مكان (PUSH_PUBLIC / ?push=1 / التطبيق المثبَّت): خارجها تعرض الصفحة سطراً «قيد التجربة» فقط.
⚠️ noindex بقصد (محتواها 100% من localStorage): مستبعدة من sitemap.xml (`make_sitemap.py::SKIP_FILES`) وبالمولَّدات (`generated_paths.txt`, `.gitignore`).

صفر طلبات API. التشغيل:
    python make_notifications.py
"""
import json
import sys

from config import BASE_DIR, LEAGUES
from i18n import T, DIR, league_name
from navbar import NAV_CSS, navbar, settings_overlay, nav_script, pwa_script, appbar
from prefs import prefs_script
import push_ui
from theme import VARS, THEME_HEAD, THEME_SCRIPT, head_meta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSS = """
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:"Segoe UI",Tahoma,sans-serif; background:var(--bg); color:var(--text); padding:24px 16px 96px; line-height:1.6; }
  .wrap { max-width:900px; margin:0 auto; }
  header h1 { font-size:22px; margin:6px 0 14px; }
  .ntabs { display:flex; gap:8px; margin-bottom:14px; }
  .ntab { flex:1; min-height:44px; border-radius:12px; border:1px solid var(--line); background:var(--card); color:var(--muted);
          font:inherit; font-size:15px; cursor:pointer; }
  .ntab.on { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:700; }
  .nview[hidden], .ntabs[hidden], #nviews[hidden], .nbeta[hidden] { display:none; }
  .nsec { color:var(--muted); font-size:13px; margin:18px 4px 8px; }
  .nrow { display:flex; align-items:center; gap:12px; background:var(--card); border-radius:12px; padding:10px 12px; margin-bottom:8px; min-height:60px; }
  .nrow img { width:36px; height:36px; object-fit:contain; flex:0 0 auto; }
  .nrow .nic { width:36px; height:36px; flex:0 0 auto; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:20px; }
  .nrow .ntx { flex:1; min-width:0; }
  .nrow .nn { font-size:15px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; display:block; color:var(--text); text-decoration:none; }
  .nrow .ns { font-size:12px; color:var(--muted); }
  .nrow .pbwrap { flex:0 0 auto; }
  .nempty { color:var(--muted); text-align:center; padding:28px 12px; font-size:14px; }
  .nbeta { background:var(--card); border-radius:12px; padding:16px; color:var(--muted); font-size:14px; text-align:center; }
"""

SCRIPT = """<script>
(function(){
  var P=window.FBPush,FB=window.FBPrefs,LG=__LG__,S=P&&P.S;
  var ptab='t', msg=document.getElementById('pushmsg');
  var teamsBox=document.getElementById('nt'),leaguesBox=document.getElementById('nl');
  var beta=document.getElementById('nbeta'),views=document.getElementById('nviews');
  if(!P||!FB)return;
  if(!P.gate()){beta.hidden=false;views.hidden=true;document.querySelector('.ntabs').hidden=true;return;}
  var sup=P.support();
  if(sup){msg.textContent=S[sup];msg.hidden=false;}
  var LANG="__LANG__",teamRows={};
  function ready(){var d=window.FBFollowData;if(d&&d.teams)d.teams.forEach(function(r){teamRows[r[0]]={ar:r[1],en:r[2],logo:r[3]};});}
  function el(tag,cls,txt){var e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;}
  function bellSvg(){var d=document.createElement('span');
    d.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>';return d.firstChild;}
  function summ(k,id){var n=P.summary(k,id);return n>=7?S.n_all:(n+' '+S.n_types);}
  function row(k,id,name,logo,href,ko){
    var r=el('div','nrow');
    if(logo){var im=document.createElement('img');im.src=logo;im.alt='';im.loading='lazy';r.appendChild(im);}
    else r.appendChild(el('span','nic',k==='l'?'\\u{1F3C6}':'\\u26BD'));
    var tx=el('div','ntx'),n=href?el('a','nn',name):el('span','nn',name);if(href)n.href=href;tx.appendChild(n);
    var on=P.has(k,id);
    tx.appendChild(el('div','ns',on?summ(k,id):''));
    r.appendChild(tx);
    var w=el('span','pbwrap'),b=el('button','bellbtn');b.type='button';b.setAttribute('aria-pressed',on?'true':'false');
    b.setAttribute('aria-label',name);b.title=name;b.appendChild(bellSvg());
    if(sup)b.disabled=true;
    b.addEventListener('click',function(){P.toggle(k,id,ko||0,msg,k==='m'?name:'');});
    w.appendChild(b);
    var ed=el('button','pbedit',S.edit);ed.type='button';ed.hidden=!on||!!sup;
    ed.addEventListener('click',function(){P.openSheet(k,id,msg);});
    w.appendChild(ed);r.appendChild(w);return r;
  }
  function render(){
    ready();teamsBox.innerHTML='';leaguesBox.innerHTML='';
    // الفرق = المتابَعة ∪ المفعَّل تنبيهها (المفعَّلة أولاً)
    var set={};FB.getClubs().forEach(function(x){set[x]=1;});P.lists.teams().forEach(function(x){set[x]=1;});
    var ids=Object.keys(set).map(Number).sort(function(a,b){
      var pa=P.has('t',a)?0:1,pb=P.has('t',b)?0:1;if(pa!==pb)return pa-pb;
      var na=(teamRows[a]||{})[LANG]||'',nb=(teamRows[b]||{})[LANG]||'';return na<nb?-1:(na>nb?1:0);});
    if(!ids.length)teamsBox.appendChild(el('div','nempty',S.n_empty_t));
    ids.forEach(function(id){var t=teamRows[id]||{};
      teamsBox.appendChild(row('t',id,t[LANG]||('#'+id),t.logo,'clubs/'+id+'.html'));});
    var ms=P.lists.matches();
    if(ms.length){
      teamsBox.appendChild(el('div','nsec',S.n_matches));
      ms.forEach(function(id){teamsBox.appendChild(row('m',id,P.label('m',id)||(S.n_match+' #'+id),null,'matches/'+id+'.html'));});
    }
    LG.forEach(function(l){leaguesBox.appendChild(row('l',l.id,l.name,null,null));});
  }
  document.querySelectorAll('.ntab').forEach(function(b){b.addEventListener('click',function(){
    ptab=b.getAttribute('data-t');
    document.querySelectorAll('.ntab').forEach(function(x){x.classList.toggle('on',x===b);});
    teamsBox.hidden=ptab!=='t';leaguesBox.hidden=ptab!=='l';});});
  P.onChange(render);
  render();
  var d=document.createElement('script');d.src="__UP__follow_data.js";d.onload=render;d.onerror=render;document.head.appendChild(d);
})();
</script>"""


def page(lang):
    t = T[lang]
    S = push_ui.STR[lang]
    depth = 0 if lang == "ar" else 1
    up = "" if lang == "ar" else "../"
    switch = "en/notifications.html" if lang == "ar" else "../notifications.html"
    title = f'{S["n_title"]} — {t["site_title"]}'
    leagues = [{"id": v["id"], "name": league_name(code, lang)} for code, v in LEAGUES.items()]
    script = (SCRIPT.replace("__LG__", json.dumps(leagues, ensure_ascii=False)).replace("__LANG__", lang).replace("__UP__", up))
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}" dir="{DIR[lang]}">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{title}</title>\n'
        '<meta name="robots" content="noindex">\n'
        + head_meta(title, t["site_sub"], up, lang, "notifications.html" if lang == "ar" else "en/notifications.html")
        + THEME_HEAD + "<style>" + VARS + CSS + NAV_CSS + push_ui.CSS + "</style>" +
        '</head>\n<body>\n<div class="wrap">\n'
        + appbar(t, lang, switch, back=True) +
        f'<header><h1>{S["n_title"]}</h1></header>\n'
        + push_ui.msg_html() +
        f'<div class="ntabs"><button class="ntab on" data-t="t">{S["n_teams"]}</button>'
        f'<button class="ntab" data-t="l">{S["n_leagues"]}</button></div>\n'
        f'<div id="nbeta" class="nbeta" hidden>{S["n_beta"]}</div>\n'
        '<div id="nviews"><div class="nview" id="nt"></div><div class="nview" id="nl" hidden></div></div>\n'
        '</div>\n'
        + navbar(t, depth, "", lang)
        + settings_overlay(t, switch, lang)
        + THEME_SCRIPT + prefs_script()
        + push_ui.engine_script(lang)
        + script
        + nav_script(t) + pwa_script(lang) +
        '</body>\n</html>'
    )


def main():
    (BASE_DIR / "en").mkdir(exist_ok=True)
    for lang, path in (("ar", BASE_DIR / "notifications.html"), ("en", BASE_DIR / "en" / "notifications.html")):
        path.write_text(page(lang), encoding="utf-8")
        print(f"  {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
