#!/usr/bin/env python3
"""
محرّك تنبيهات المتصفح المشترك (13 أكتوبر 2026، دفعة 3E) — نادٍ · مباراة · دوري بأنواع تنبيه قابلة للتعديل
==========================================================================================================
مصدر واحد لكل ما يخص اشتراك الدفع بالمتصفح، تستعمله صفحات النادي والمباراة والدوري وصفحة الإشعارات (`window.FBPush`):

  • الحالة محلية بـlocalStorage:
      fbPushTeams    [team_id,…]                       (المفتاح القديم نفسه — لا هجرة للمشتركين الحاليين)
      fbPushMatches  [[match_id, انطلاق ms],…]         (تنتهي صلاحيتها بعد 14 يوماً من الانطلاق؛ صفحة الإشعارات تُخفي المنتهية بـprune)
      fbPushLeagues  [league_id,…]                     (معرّف المزوّد: 233 مصر…)
      fbPushTypes    {"t:962": قناع, "m:77": قناع, "l:233": قناع}   (غائب = 127 = الكل)
      fbPushOn       '1' علامة وجود اشتراك (القديم)
  • أنواع التنبيه (قناع بتّات، يطابق الـworker): 1 انطلاق · 2 هدف · 4 نهاية الشوط الأول · 8 بداية الثاني · 16 نهاية المباراة · 32 بطاقة حمراء · 64 تذكير قبل 30 د.
    · 128 ضربة جزاء ضائعة · 256 التشكيلة الرسمية (19 أكتوبر 2026). الاشتراك الجديد = DEF (499، بلا بداية الشوط الثاني ولا نهاية الأول).
  • **الجرس = تشغيل/إيقاف كل الأنواع بنقرة**، وتحته رابط صغير «تعديل/Edit» يفتح ورقة سفلية بالأنواع (يظهر والجرس مفعَّل فقط).
  • كل مزامنة ترسل لـ/push/subscribe **الحالة كاملة** (teams+tt, matches+mt, leagues+lt, lang): الـAPI يستبدلها كمجموعة، وغياب الأقنعة = الكل على الخادم.
    إزالة آخر كيان (من أي نوع) = /push/unsubscribe. الإذن يُطلب من داخل النقرة (شرط iOS).
  • البوّابة كما كانت: PUSH_PUBLIC أو ?push=1 أو التطبيق المثبَّت؛ iPhone بلا تثبيت يرى تلميح «أضف الموقع للشاشة الرئيسية».
"""
import json

from config import LEAGUES

PUSH_WORKER = "https://saffara-live.abujaishamr.workers.dev"

TYPE_ROWS = [  # (bit, مفتاح الترجمة) — ترتيب عمرو (18 أكتوبر، دفعة B)
    (1, "t_ko"), (4, "t_ht"), (16, "t_ft"), (2, "t_goal"), (32, "t_red"), (128, "t_mp"), (256, "t_lineup"), (64, "t_rem"),
]
# ⚠️ بداية الشوط الثاني (8) مخفية من الواجهة فقط: تبقى بالأقنعة المخزَّنة كما هي (الورقة لا تمسّها أبداً)، وALL = 511.
# التشكيلة (256، 19 أكتوبر 2026): بـDEF للاشتراك الجديد فقط (499)؛ الأقنعة المحفوظة لا تتغيّر (المشترك الحالي يفعّلها من الورقة).

STR = {
    "ar": {
        "on_t": "تنبيهات هذا النادي مفعّلة.", "on_m": "تنبيهات هذه المباراة مفعّلة.", "on_l": "تنبيهات هذا الدوري مفعّلة.",
        "off_t": "أُوقفت تنبيهات هذا النادي.", "off_m": "أُوقفت تنبيهات هذه المباراة.", "off_l": "أُوقفت تنبيهات هذا الدوري.",
        "off": "أُوقفت التنبيهات.",
        "unsupported": "التنبيهات غير مدعومة هنا. على الآيفون أضِف الموقع إلى الشاشة الرئيسية ثم افتحه منها.",
        "ios": "أضف الموقع للشاشة الرئيسية لتفعيل التنبيهات",
        "denied": "الإذن محظور من إعدادات المتصفح.", "dismissed": "لم يُمنح الإذن.",
        "rate": "محاولات كثيرة، حاول بعد قليل.", "full": "التنبيهات ممتلئة حالياً، حاول لاحقاً.",
        "toomany_t": "الحد الأقصى 50 نادياً للتنبيهات.", "toomany_m": "الحد الأقصى 20 مباراة للتنبيهات.", "toomany_l": "الحد الأقصى __NL__ دوريات.",
        "error": "تعذّر التفعيل، حاول لاحقاً.",
        "label_t": "تنبيهات هذا النادي", "label_m": "تنبيهات هذه المباراة", "label_l": "تنبيهات هذا الدوري",
        "edit": "تعديل", "sheet_title": "أنواع التنبيهات", "done": "تم", "n_title": "الإشعارات", "n_teams": "الفرق", "n_leagues": "الدوريات", "n_matches": "مباريات",
        "n_empty_t": "لا فرق بعد. فعّل جرس أي نادٍ من صفحته أو تابعه ليظهر هنا.", "n_empty_m": "لا مباريات.", "n_beta": "التنبيهات قيد التجربة وستتاح للجميع قريباً.",
        "n_types": "أنواع", "n_all": "كل الأنواع", "n_match": "مباراة",
        "n_master": "كل التنبيهات", "n_master_off": "التنبيهات متوقفة. خياراتك محفوظة وتعود عند التشغيل.", "master_on": "عادت التنبيهات بخياراتك المحفوظة.", "master_off": "أُوقفت كل التنبيهات.",
        "t_ko": "انطلاق المباراة", "t_goal": "الأهداف", "t_mp": "ضربة جزاء ضائعة", "t_ht": "نهاية الشوط الأول", "t_sh": "بداية الشوط الثاني",
        "t_ft": "نهاية المباراة", "t_red": "البطاقات الحمراء", "t_rem": "تذكير بالمباراة", "t_lineup": "التشكيلة",
        "toast_on": "تم تفعيل إشعارات {x}", "toast_off": "تم إيقاف إشعارات {x}", "set_alerts": "ضبط التنبيهات", "n_enabled": "الإشعارات مفعّلة",
    },
    "en": {
        "on_t": "Alerts are on for this club.", "on_m": "Alerts are on for this match.", "on_l": "Alerts are on for this league.",
        "off_t": "Alerts for this club are off.", "off_m": "Alerts for this match are off.", "off_l": "Alerts for this league are off.",
        "off": "Alerts are off.",
        "unsupported": "Alerts aren't supported here. On iPhone, add the site to your Home Screen and open it from there.",
        "ios": "Add the site to your Home Screen to turn on alerts",
        "denied": "Permission is blocked in your browser settings.", "dismissed": "Permission wasn't granted.",
        "rate": "Too many attempts, try again in a little while.", "full": "Alerts are full right now, please try again later.",
        "toomany_t": "You can get alerts for up to 50 clubs.", "toomany_m": "You can get alerts for up to 20 matches.", "toomany_l": "Up to __NL__ leagues.",
        "error": "Couldn't turn on alerts. Try again later.",
        "label_t": "Alerts for this club", "label_m": "Alerts for this match", "label_l": "Alerts for this league",
        "edit": "Edit", "sheet_title": "Alert types", "done": "Done", "n_title": "Notifications", "n_teams": "Teams", "n_leagues": "Leagues", "n_matches": "Matches",
        "n_empty_t": "No teams yet. Turn on the bell on any club page or follow a club to see it here.", "n_empty_m": "No matches.", "n_beta": "Alerts are in testing and will open to everyone soon.",
        "n_types": "types", "n_all": "All types", "n_match": "Match",
        "n_master": "All alerts", "n_master_off": "Alerts are off. Your choices are saved and come back when you turn them on.", "master_on": "Alerts are back with your saved choices.", "master_off": "All alerts are off.",
        "t_ko": "Started", "t_goal": "Goals", "t_mp": "Missed penalty", "t_ht": "Half time", "t_sh": "Second half", "t_ft": "Full time",
        "t_red": "Red cards", "t_rem": "Match reminder", "t_lineup": "Lineup",
        "toast_on": "Notifications for {x} enabled", "toast_off": "Notifications for {x} disabled", "set_alerts": "Set alerts", "n_enabled": "Notifications enabled",
    },
}

CSS = """
  /* جرس التنبيهات + رابط «تعديل» تحته + الورقة السفلية بأنواع التنبيه (13 أكتوبر، 3E) */
  .bellbtn { flex:0 0 auto; width:44px; height:44px; border-radius:50%; padding:0; cursor:pointer;
             display:inline-flex; align-items:center; justify-content:center;
             background:transparent; color:var(--muted); border:1px solid var(--line); }
  .bellbtn[hidden] { display:none; }
  .bellbtn svg { width:22px; height:22px; fill:none; stroke:currentColor; stroke-width:1.8;
                 stroke-linecap:round; stroke-linejoin:round; }
  .bellbtn[aria-pressed="true"] { background:var(--accent); border-color:var(--accent); color:#fff; }
  .bellbtn[aria-pressed="true"] svg { fill:currentColor; }
  .bellbtn:disabled { opacity:.55; cursor:default; }
  .pushmsg { color:var(--muted); font-size:13px; margin:0 0 14px; padding-inline:4px; }
  .pushmsg[hidden] { display:none; }
  /* ⚠️ (14 أكتوبر) الغلاف بحجم الجرس الثابت 44×44 و«تعديل» مطلق تحته: ظهوره/اختفاؤه لا يغيّر مكان الجرس أبداً (كان بالتدفق
     العادي فيكبر الغلاف ويرتفع الجرس عن النجمة والترس). الغلاف بلا جرس ظاهر (غير مدعوم) يختفي كي لا يحجز فراغاً. */
  .pbwrap { position:relative; display:inline-flex; align-items:center; justify-content:center;
            width:44px; height:44px; flex:0 0 44px; }
  .pbwrap:not(:has(.bellbtn:not([hidden]), .mact:not([hidden]))) { display:none; }
  .pbedit { position:absolute; top:100%; left:50%; transform:translateX(-50%); z-index:3;
            white-space:nowrap; background:none; border:none; padding:0 4px; margin-top:1px; color:var(--accent); font:inherit;
            font-size:11px; line-height:1.2; cursor:pointer; text-decoration:underline; }
  .pbedit[hidden] { display:none; }
  /* الصفوف تحجز مكان «تعديل» تحت الجرس دائماً (لا قفزة عند التفعيل) — جرس المباراة بلا «تعديل» (دفعة B) فلا حجز */
  .appbar:has(.pbedit), .hdract:has(.pbedit) { padding-bottom:14px; }
  /* جرس المباراة (دفعة B): ممتلئ مفعَّلاً، محدَّد بخط مائل مطفأً */
  .pbx { display:none; }
  [aria-pressed="false"] > svg .pbx { display:inline; }
  /* إشعار سفلي مؤقت فوق شريط التنقل (دفعة B): حالة الجرس + «تعديل»، والأخطاء بلا رابط */
  .ptoast { position:fixed; inset-inline:16px; bottom:calc(78px + env(safe-area-inset-bottom)); z-index:980; max-width:480px; margin:0 auto;
            display:flex; align-items:center; justify-content:space-between; gap:12px; padding:12px 16px; border-radius:12px;
            background:var(--card2); color:var(--text); border:1px solid var(--line); box-shadow:0 6px 20px rgba(0,0,0,.25); font-size:14px; }
  .ptoast[hidden] { display:none; }
  .ptoast .ptlink { flex:0 0 auto; background:none; border:none; padding:4px 0; color:var(--accent); font:inherit; font-weight:700; cursor:pointer; }
  /* مفتاح تشغيل/إيقاف (مشترك: صفحة الإشعارات + ورقة الأنواع) */
  .switch { position:relative; width:52px; height:30px; flex:0 0 auto; }
  .switch input { opacity:0; width:100%; height:100%; margin:0; position:absolute; inset:0; cursor:pointer; z-index:2; }
  .switch .trk { position:absolute; inset:0; border-radius:15px; background:var(--line); transition:.15s; }
  .switch .trk::after { content:""; position:absolute; top:3px; inset-inline-start:3px; width:24px; height:24px; border-radius:50%; background:#fff; transition:.15s; }
  .switch input:checked + .trk { background:var(--accent); }
  .switch input:checked + .trk::after { inset-inline-start:25px; }
  .psheet { position:fixed; inset:0; z-index:960; display:none; align-items:flex-end; justify-content:center;
            background:rgba(0,0,0,.55); }
  .psheet.on { display:flex; }
  .pbox { background:var(--card); color:var(--text); width:100%; max-width:480px; border-radius:16px 16px 0 0;
          padding:18px 16px 22px; border:1px solid var(--line); border-bottom:none; max-height:80vh; overflow:auto; }
  .pbox h3 { font-size:16px; margin:0 0 4px; }
  .pbox .psub { color:var(--muted); font-size:13px; margin-bottom:10px; }
  .prow { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:46px;
          border-bottom:1px solid var(--line); font-size:15px; cursor:pointer; }
  .prow:last-of-type { border-bottom:none; }
  /* دوائر اختيار 24px (دفعة B): مربع الاختيار الأصلي نفسه (للوصولية) بمظهر دائري */
  .prow input { appearance:none; -webkit-appearance:none; margin:0; width:24px; height:24px; flex:0 0 auto; border-radius:50%;
                border:2px solid var(--line); background:transparent; display:inline-grid; place-content:center; cursor:pointer; }
  .prow input::after { content:""; width:6px; height:11px; border:solid #fff; border-width:0 2px 2px 0; transform:translateY(-1px) rotate(45deg); display:none; }
  .prow input:checked { background:var(--accent); border-color:var(--accent); }
  .prow input:checked::after { display:block; }
  .prow input:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .pmaster { display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:52px; font-size:15px; font-weight:700;
             border-bottom:1px solid var(--line); margin-bottom:4px; }
  .plist.off .prow { opacity:.45; }
  .plist.off .prow input { cursor:default; }
  .pdone { margin-top:14px; width:100%; min-height:44px; border-radius:12px; border:none; background:var(--accent); color:#fff;
           font:inherit; font-size:15px; font-weight:700; cursor:pointer; }
"""


def engine_script(lang):
    """<script> المحرّك المشترك (window.FBPush) — يُحقن بأي صفحة فيها جرس. آمن لو حُقن مرتين."""
    # حدّ الدوريات = عدد الدوريات المفعَّلة (config.LEAGUES: 7 اليوم، 24 أكتوبر 2026) — يتبع ENABLED_LEAGUES بلا تعديل هنا (وLEAGUE_IDS بالـworker)
    S = json.dumps(STR[lang], ensure_ascii=False).replace("__NL__", str(len(LEAGUES)))
    from make_clubs import PUSH_PUBLIC   # الثابت الوحيد لإطلاق التنبيهات للجميع (يقلبه القرار الصريح)
    return (ENGINE_JS.replace("__S__", S).replace("__LANG__", lang).replace("__W__", PUSH_WORKER)
            .replace("__PUB__", "true" if PUSH_PUBLIC else "false")
            .replace("__ROWS__", json.dumps([[b, k] for b, k in TYPE_ROWS])).replace("__NL__", str(len(LEAGUES))))


def engine_body(lang):
    """نفس المحرّك بلا وسم <script> (لتجميعه مع سكربت ربط بكتلة واحدة)."""
    t = engine_script(lang).strip()
    return t[len("<script>"):-len("</script>")]


def bell_html(kind, ident, lang, ko_iso="", bell_class="bellbtn", extra_wrap="", label="", edit=True, strike=False):
    """جرس + رابط «تعديل» تحته (مخفيان حتى يكشفهما المحرّك). kind: t|m|l. الجرس id=pushbtn والتعديل id=pushedit.
    edit=False (جرس المباراة، دفعة B): بلا «تعديل» — الإشعار السفلي يحمل الرابط. strike=True: خط مائل على الجرس المطفأ."""
    lab = STR[lang]["label_" + kind]
    return (f'<span class="pbwrap{extra_wrap}">'
            f'<button class="{bell_class}" id="pushbtn" type="button" aria-pressed="false" hidden data-kind="{kind}" data-id="{ident}" '
            f'data-ko="{ko_iso}" data-label="{label}" aria-label="{lab}" title="{lab}">'
            f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
            f'<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>' + ('<path class="pbx" d="M3 3l18 18"/>' if strike else '') + '</svg></button>'
            + (f'<button class="pbedit" id="pushedit" type="button" hidden>{STR[lang]["edit"]}</button>' if edit else '') + '</span>')


def page_script(lang, fallback_tid=False):
    """سكربت الربط لصفحة بجرس واحد (الدوري…): المحرّك + bind على #pushbtn/#pushedit/#pushmsg."""
    return ("<script>" + engine_body(lang) + "\n"
            "(function(){var b=document.getElementById('pushbtn');if(!b||!window.FBPush)return;"
            "window.FBPush.bind(b,document.getElementById('pushedit'),document.getElementById('pushmsg'));})();</script>")


def msg_html():
    return '<div class="pushmsg" id="pushmsg" role="status" hidden></div>\n'


ENGINE_JS = """<script>
(function(){
if(window.FBPush)return;
var W="__W__",LANG="__LANG__",S=__S__,PUB=__PUB__,ROWS=__ROWS__,MAXT=50,MAXM=20,MAXL=__NL__,ALL=511,DEF=499,LEGACY=2,DAY=86400000,HOUR=3600000;
function lsGet(k){try{return localStorage.getItem(k);}catch(e){return null;}}
function lsSet(k,v){try{if(v==null)localStorage.removeItem(k);else localStorage.setItem(k,v);}catch(e){}}
function jget(k,d){try{var v=JSON.parse(lsGet(k)||'null');return v==null?d:v;}catch(e){return d;}}
function ints(a){return Array.isArray(a)?a.filter(Number.isInteger):[];}
/* البوّابة: PUSH_PUBLIC أو ?push=1 أو التطبيق المثبَّت */
var standalone=false;
try{standalone=window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;}catch(e){}
var on=PUB;
try{if(new URLSearchParams(location.search).get('push')==='1')on=true;}catch(e){}
if(standalone)on=true;
var ios=false;
try{ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);}catch(e){}
function support(){
  if(ios&&!standalone)return 'ios';
  if(!('serviceWorker' in navigator)||!('PushManager' in window)||!('Notification' in window))return 'unsupported';
  return null;
}
/* الحالة */
function teams(){return ints(jget('fbPushTeams',[])).slice(0,MAXT);}
function matchPairs(){
  var a=jget('fbPushMatches',[]);if(!Array.isArray(a))a=[];var now=Date.now();
  return a.filter(function(x){return Array.isArray(x)&&Number.isInteger(x[0])&&!(x[1]&&x[1]+14*DAY<now);}).slice(0,MAXM);
}
function leagues(){return ints(jget('fbPushLeagues',[])).slice(0,MAXL);}
function types(){var o=jget('fbPushTypes',{});return(o&&typeof o==='object'&&!Array.isArray(o))?o:{};}
function key(k,id){return k+':'+id;}
function list(k){return k==='t'?teams():k==='l'?leagues():matchPairs().map(function(x){return x[0];});}
function has(k,id){return list(k).indexOf(id)>=0;}
/* قناع غائب = اشتراك قديم (ما قبل 3E: أهداف فقط)؛ الاشتراك الجديد يكتب قناعه صراحةً (DEF) */
function maskOf(k,id){var m=types()[key(k,id)];return(Number.isInteger(m)&&m>=1&&m<=ALL)?m:LEGACY;}
function total(){return teams().length+matchPairs().length+leagues().length;}
/* مفتاح «كل التنبيهات» (3E2): fbPushMaster='off' = لا تنبيهات إطلاقاً (الاشتراك بالخادم والمتصفح يُلغى) مع بقاء القوائم والأقنعة المحلية كما هي؛
   إعادة التشغيل تعيد اشتراك الحالة المحفوظة كاملة. غائب = مفعَّل. */
function master(){return lsGet('fbPushMaster')!=='off';}
function active(k,id){return master()&&has(k,id);}
function saveList(k,arr){
  if(k==='t')lsSet('fbPushTeams',arr.length?JSON.stringify(arr):null);
  else if(k==='l')lsSet('fbPushLeagues',arr.length?JSON.stringify(arr):null);
  else lsSet('fbPushMatches',arr.length?JSON.stringify(arr):null);
}
function setMask(k,id,m){var t=types();if(m==null)delete t[key(k,id)];else t[key(k,id)]=m;
  lsSet('fbPushTypes',Object.keys(t).length?JSON.stringify(t):null);}
function snapshot(){return {ms:lsGet('fbPushMaster'),t:lsGet('fbPushTeams'),m:lsGet('fbPushMatches'),l:lsGet('fbPushLeagues'),y:lsGet('fbPushTypes'),o:lsGet('fbPushOn'),b:lsGet('fbPushLabels')};}
function restore(s){lsSet('fbPushMaster',s.ms);lsSet('fbPushTeams',s.t);lsSet('fbPushMatches',s.m);lsSet('fbPushLeagues',s.l);lsSet('fbPushTypes',s.y);lsSet('fbPushOn',s.o);lsSet('fbPushLabels',s.b);}
function labels(){var o=jget('fbPushLabels',{});return(o&&typeof o==='object'&&!Array.isArray(o))?o:{};}
function setLabel(k,id,v){var o=labels();if(v)o[key(k,id)]=String(v).slice(0,80);else delete o[key(k,id)];
  lsSet('fbPushLabels',Object.keys(o).length?JSON.stringify(o):null);}
function label(k,id){return labels()[key(k,id)]||'';}
function summary(k,id){var m=maskOf(k,id),n=0;ROWS.forEach(function(r){if(m&r[0])n++;});return n;}
function nTypes(){return ROWS.length;}
function add(k,id,ko,lab){
  if(lab)setLabel(k,id,lab);
  if(k==='m'){var a=matchPairs().filter(function(x){return x[0]!==id;});a.push([id,ko||0]);saveList('m',a);}
  else{var b=list(k).filter(function(x){return x!==id;});b.push(id);saveList(k,b);}
  setMask(k,id,DEF);
}
function remove(k,id){
  setLabel(k,id,'');
  if(k==='m')saveList('m',matchPairs().filter(function(x){return x[0]!==id;}));
  else saveList(k,list(k).filter(function(x){return x!==id;}));
  setMask(k,id,null);
}
function limitFor(k){return k==='t'?MAXT:(k==='m'?MAXM:MAXL);}
/* خادم */
function key2arr(k){var p='='.repeat((4-k.length%4)%4),b=atob((k+p).replace(/-/g,'+').replace(/_/g,'/'));
  var u=new Uint8Array(b.length);for(var i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u;}
function post(path,body){return fetch(W+path,{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(body)}).then(function(r){if(!r.ok)throw new Error(String(r.status));return r.json();});}
function errKey(e){var m=e&&e.message;return m==='429'?'rate':(m==='503'?'full':'error');}
function getSub(){return navigator.serviceWorker.ready.then(function(reg){return reg.pushManager.getSubscription();});}
function body(sub){
  var tt={},mt={},lt={};
  var T=teams(),M=matchPairs().map(function(x){return x[0];}),L=leagues();
  T.forEach(function(id){tt[id]=maskOf('t',id);});M.forEach(function(id){mt[id]=maskOf('m',id);});L.forEach(function(id){lt[id]=maskOf('l',id);});
  return {subscription:sub.toJSON?sub.toJSON():sub,teams:T,tt:tt,matches:M,mt:mt,leagues:L,lt:lt,lang:LANG};
}
/* نقل المشتركين القدامى (fbPushOn=1 بلا fbPushTeams): القائمة = ما هو مسجَّل فعلاً لهذا الاشتراك، وإلا النادي الحالي فقط */
function migrate(sub,fallbackTid){
  if(lsGet('fbPushTeams')!==null||lsGet('fbPushOn')!=='1'||!sub)return Promise.resolve();
  var j=sub.toJSON();
  return post('/push/teams',{endpoint:j.endpoint,auth:j.keys.auth}).then(function(r){
    var a=(r&&Array.isArray(r.teams))?r.teams.filter(Number.isInteger):[];
    saveList('t',a.length?a:(fallbackTid?[fallbackTid]:[]));})
  .catch(function(){if(fallbackTid)saveList('t',[fallbackTid]);});
}
/* يضبط الاشتراك الفعلي على القوائم المحلية. enable=true (من نقرة): يطلب الإذن/ينشئ الاشتراك عند الحاجة. */
function apply(enable){
  if(total()===0||!master()){
    return getSub().then(function(sub){
      if(!sub)return;var j=sub.toJSON();
      return post('/push/unsubscribe',{endpoint:j.endpoint,auth:j.keys.auth}).then(function(){return sub.unsubscribe();});
    }).then(function(){lsSet('fbPushOn',null);});
  }
  var created=false,sub0=null;
  var step=enable?Notification.requestPermission().then(function(p){
    if(p!=='granted'){var e=new Error('perm');e.perm=p;throw e;}
    return navigator.serviceWorker.ready;
  }):navigator.serviceWorker.ready;
  return step.then(function(reg){
    return fetch(W+'/push/key').then(function(r){return r.json();}).then(function(k){
      return reg.pushManager.getSubscription().then(function(s){
        if(s)return s;created=true;
        return reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key2arr(k.key)});});});})
  .then(function(sub){sub0=sub;return post('/push/subscribe',body(sub));})
  .then(function(){lsSet('fbPushOn','1');})
  .catch(function(e){if(created&&sub0){try{sub0.unsubscribe();}catch(x){}}throw e;});
}
var busy=false;
var listeners=[];
function emit(){listeners.forEach(function(f){try{f();}catch(e){}});}
/* msgEl إما سطر رسالة (#pushmsg) وإما مستقبِل إشعار سفلي {toast:fn} (جرس المباراة، دفعة B) */
function say(k,msgEl){if(!msgEl)return;if(msgEl.toast){if(k)msgEl.toast(k);return;}msgEl.textContent=k?(S[k]||''):'';msgEl.hidden=!k;}
/* تشغيل/إيقاف كل الأنواع لكيان بنقرة. يرجع Promise<bool> (true=نجح). mask (اختياري، من مفتاح الورقة): قناع التشغيل بدل الافتراضي */
function toggle(k,id,ko,msgEl,lab,mask){
  if(busy)return Promise.resolve(false);
  busy=true;say('',msgEl);
  var snap=snapshot(),was=has(k,id)&&master();
  if(!master())lsSet('fbPushMaster',null);   // نقرة جرس والمفتاح العام مطفأ: يعود المفتاح للتشغيل (تُستعاد الخيارات المحفوظة) وهذا الكيان يصير مفعَّلاً
  if(was)remove(k,id);
  else if(has(k,id)){}
  else{
    if(list(k).length>=limitFor(k)){say('toomany_'+k,msgEl);busy=false;return Promise.resolve(false);}
    add(k,id,ko,lab);
    if(mask)setMask(k,id,mask);
  }
  return apply(!was).then(function(){say(was?'off_'+k:'on_'+k,msgEl);busy=false;emit();return true;})
  .catch(function(e){
    restore(snap);
    say(e&&e.perm?(e.perm==='denied'?'denied':'dismissed'):errKey(e),msgEl);
    busy=false;emit();return false;});
}
/* تعديل أنواع كيان مفعَّل (بلا طلب إذن): قناع 0 = إيقاف الكيان */
function setTypes(k,id,mask,msgEl){
  if(!has(k,id))return Promise.resolve(false);
  var snap=snapshot();
  if(!mask){remove(k,id);}else setMask(k,id,mask);
  return apply(false).then(function(){emit();return true;}).catch(function(e){restore(snap);say(errKey(e),msgEl);emit();return false;});
}
/* إخفاء المباريات المنتهية (18 أكتوبر): finishedIds = حالتها FT/AET/PEN بـf من الردّ الحيّ (null = تعذّر الجلب، القاعدة تُتخطّى)؛
   holdIds = جارية (m) أو بحالة غير نهائية بـf (PST/مؤجلة…) فلا تُخفى أبداً. احتياط: انطلاق + 4 ساعات مضت ولا هي بـholdIds.
   بلا موعد انطلاق (0) = قاعدة الـ14 يوماً بـmatchPairs كما هي. حُذف شيء والاشتراك قائم والجلب نجح → apply(false) يستبدل مجموعة الخادم. */
function prune(finishedIds,holdIds){
  var F={},H={},now=Date.now();
  (finishedIds||[]).forEach(function(x){F[x]=1;});(holdIds||[]).forEach(function(x){H[x]=1;});
  var a=matchPairs(),keep=a.filter(function(x){
    if(F[x[0]])return false;
    return !(x[1]&&x[1]+4*HOUR<now&&!H[x[0]]);});
  if(keep.length===a.length)return Promise.resolve(false);
  a.forEach(function(x){if(keep.indexOf(x)<0){setLabel('m',x[0],'');setMask('m',x[0],null);}});
  saveList('m',keep);
  // تعذّر الجلب الحي (finishedIds === null): إخفاء محلي فقط — مجموعة الخادم لا تُستبدل إلا بعد جلب ناجح
  if(finishedIds===null||!('serviceWorker' in navigator)){emit();return Promise.resolve(true);}
  return getSub().then(function(sub){if(sub)return apply(false);})
  .catch(function(){}).then(function(){emit();return true;});
}
/* المفتاح العام: off يُلغي الاشتراك ويحتفظ بالقوائم؛ on يطلب الإذن (من داخل النقرة) ويعيد اشتراك المحفوظ كاملاً */
function setMaster(on,msgEl){
  if(busy)return Promise.resolve(false);
  busy=true;say('',msgEl);
  var snap=snapshot();
  lsSet('fbPushMaster',on?null:'off');
  return apply(on&&total()>0).then(function(){say(on?'master_on':'master_off',msgEl);busy=false;emit();return true;})
  .catch(function(e){restore(snap);say(e&&e.perm?(e.perm==='denied'?'denied':'dismissed'):errKey(e),msgEl);busy=false;emit();return false;});
}
/* الورقة السفلية «ضبط التنبيهات» (دفعة B): مفتاح «الإشعارات مفعّلة» (إيقافه = إزالة الكيان، الصفوف تُعتَّم وتبقى) + دوائر الأنواع، حفظ فوري.
   الأنواع المخفية (بداية الشوط الثاني 8) تُحفظ كما هي بأي تعديل. ctx {ko, lab}: فتحها والكيان مطفأ (من الإشعار السفلي). */
var VIS=0;ROWS.forEach(function(r){VIS|=r[0];});
var HID=ALL&~VIS;
function dash(l){return String(l||'').replace(/\s*\u00d7\s*/,' - ');}
var sheet=null,sh={};
function paintSheet(){
  if(!sheet||!sh.k)return;
  var on=active(sh.k,sh.id),cur=on?maskOf(sh.k,sh.id):sh.last;
  sheet.querySelector('#pmsw').checked=on;
  var box=sheet.querySelector('.plist');box.classList.toggle('off',!on);
  box.querySelectorAll('.prow input').forEach(function(i){i.checked=(cur&parseInt(i.getAttribute('data-bit'),10))!==0;i.disabled=!on;});
}
function openSheet(k,id,msgEl,ctx){
  ctx=ctx||{};
  if(!has(k,id)&&!ctx.lab&&!ctx.ko)return;
  if(!sheet){
    sheet=document.createElement('div');sheet.className='psheet';sheet.id='psheet';
    sheet.innerHTML='<div class="pbox" role="dialog" aria-modal="true"><h3></h3><div class="psub"></div>'+
      '<label class="pmaster"><span class="pml"></span><span class="switch"><input type="checkbox" id="pmsw"><span class="trk"></span></span></label>'+
      '<div class="plist"></div><button type="button" class="pdone"></button></div>';
    document.body.appendChild(sheet);
    sheet.addEventListener('click',function(e){if(e.target===sheet)closeSheet();});
    sheet.querySelector('.pdone').addEventListener('click',closeSheet);
    sheet.querySelector('#pmsw').addEventListener('change',function(){
      if(this.checked)toggle(sh.k,sh.id,sh.ko,sh.msg,sh.lab,sh.last).then(paintSheet);
      else{sh.last=maskOf(sh.k,sh.id);setTypes(sh.k,sh.id,0,sh.msg).then(paintSheet);}
    });
  }
  var lab=label(k,id)||ctx.lab||'';
  sh={k:k,id:id,msg:msgEl,ko:ctx.ko||koOf(k,id),lab:lab,last:has(k,id)?maskOf(k,id):DEF};
  sheet.querySelector('h3').textContent=(k==='m'&&lab)?dash(lab):S.sheet_title;
  sheet.querySelector('.psub').textContent=k==='m'?S.set_alerts:S['label_'+k];
  sheet.querySelector('.pml').textContent=S.n_enabled;
  sheet.querySelector('#pmsw').setAttribute('aria-label',S.n_enabled);
  sheet.querySelector('.pdone').textContent=S.done;
  var box=sheet.querySelector('.plist');box.innerHTML='';
  ROWS.forEach(function(r){
    var row=document.createElement('label');row.className='prow';
    var t=document.createElement('span');t.textContent=S[r[1]];
    var c=document.createElement('input');c.type='checkbox';c.setAttribute('data-bit',r[0]);
    c.addEventListener('change',function(){
      var v=0;box.querySelectorAll('.prow input').forEach(function(i){if(i.checked)v|=parseInt(i.getAttribute('data-bit'),10);});
      if(!v){sh.last=maskOf(k,id);setTypes(k,id,0,msgEl).then(paintSheet);return;}   // لا نوع ظاهر = إيقاف (يُتذكَّر القناع للتشغيل)
      setTypes(k,id,(maskOf(k,id)&HID)|v,msgEl).then(paintSheet);
    });
    row.appendChild(t);row.appendChild(c);box.appendChild(row);
  });
  paintSheet();
  sheet.classList.add('on');
}
function closeSheet(){if(sheet)sheet.classList.remove('on');}
function koOf(k,id){if(k!=='m')return 0;var x=matchPairs().filter(function(p){return p[0]===id;})[0];return x?x[1]:0;}
/* الإشعار السفلي المؤقت (دفعة B): 3.5 ث، role=status؛ onEdit = رابط «تعديل» يفتح الورقة (الأخطاء بلا رابط) */
var tEl=null,tTimer=0;
function toastEl(){
  if(!tEl){tEl=document.createElement('div');tEl.className='ptoast';tEl.id='ptoast';tEl.setAttribute('role','status');tEl.setAttribute('aria-live','polite');
    tEl.hidden=true;document.body.appendChild(tEl);}
  return tEl;}
function hideToast(){if(tEl)tEl.hidden=true;}
function toast(text,onEdit){
  var el=toastEl();el.innerHTML='';
  var s=document.createElement('span');s.textContent=text;el.appendChild(s);
  if(onEdit){var b=document.createElement('button');b.type='button';b.className='ptlink';b.textContent=S.edit;
    b.addEventListener('click',function(){hideToast();onEdit();});el.appendChild(b);}
  el.hidden=false;clearTimeout(tTimer);tTimer=setTimeout(hideToast,3500);
}
function toastSink(k,id,ko,lab){
  var o={toast:function(key){
    if(key==='on_'+k||key==='off_'+k){
      var x=dash(label(k,id)||lab);
      toast(S[key==='on_'+k?'toast_on':'toast_off'].replace('{x}',x),function(){openSheet(k,id,o,{ko:ko,lab:lab});});
    }else toast(S[key]||'');
  }};
  return o;
}
/* ربط جرس + رابط تعديل بكيان */
function bind(bell,edit,msgEl,opts){
  if(!bell||!on)return;
  var k=bell.getAttribute('data-kind'),id=parseInt(bell.getAttribute('data-id'),10),ko=Date.parse(bell.getAttribute('data-ko'))||0;
  bell.hidden=false;
  var sup=support();
  function paint(){var h=active(k,id);bell.setAttribute('aria-pressed',h?'true':'false');if(edit)edit.hidden=!h||!!sup;}
  paint();listeners.push(paint);
  window.addEventListener('storage',paint);
  if(sup){bell.disabled=true;say(sup,msgEl);return;}
  getSub().then(function(sub){
    if(!master()){emit();return;}
    if(!sub||Notification.permission!=='granted'){
      ['fbPushTeams','fbPushMatches','fbPushLeagues','fbPushTypes','fbPushOn','fbPushLabels'].forEach(function(x){lsSet(x,null);});
      emit();return;}
    return migrate(sub,opts&&opts.fallbackTid).then(emit);
  }).catch(function(){});
  var lab=bell.getAttribute('data-label')||'';
  // opts.toast (جرس المباراة، دفعة B): نتيجة النقرة بإشعار سفلي بدل سطر الرسالة؛ «البوّابة/الدعم» عند التحميل يبقى بالسطر
  var out=opts&&opts.toast?(toastEl(),toastSink(k,id,ko,lab)):msgEl;
  bell.addEventListener('click',function(){toggle(k,id,ko,out,lab);});
  if(edit)edit.addEventListener('click',function(){openSheet(k,id,msgEl);});
}
window.FBPush={on:on,gate:function(){return on;},support:support,has:has,active:active,master:master,setMaster:setMaster,nTypes:nTypes,maskOf:maskOf,summary:summary,label:label,toggle:toggle,setTypes:setTypes,openSheet:openSheet,prune:prune,
  bind:bind,lists:{teams:teams,matches:function(){return matchPairs().map(function(x){return x[0];});},leagues:leagues},
  onChange:function(f){listeners.push(f);},S:S};
})();
</script>"""
