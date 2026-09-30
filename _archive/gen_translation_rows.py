#!/usr/bin/env python3
"""
مولّد صفوف players_ar.csv من ملف مراجعة الترجمة (أداة مرجعية — مؤرشفة)
======================================================================
وُلدت بجلسة 30 سبتمبر 2026 (دفعات الترجمة بالبحث على الويب). تبني
الصفوف **المقيَّدة** (player_en + player_ar + player_id + team_id) التي
يقرؤها `apply_players_ar.py`، لكل لاعب عالي الثقة بملف المراجعة.

المدخل: CSV مراجعة بالأعمدة:
    player_id, name_en_db, team_id, name_ar_proposed, confidence, ...
    (الصفوف بـconfidence=high فقط تُعالَج؛ غيرها يُتجاهل)
المخرج: ملف JSON بقائمة [player_en, player_ar, player_id, team_id]

ماذا تفعل لكل لاعب:
  • تجمع **كل صيغ الاسم** للمعرّف نفسه من lineup_players/player_stats
    (الاسم المختصر والكامل) مع كل فريق ظهر به، فتُغطّى goals/events
    (بلا player_id) عبر الاسم+team_id.
  • تفحص أن أي ترجمة موجودة أصلاً بالقاعدة لا تخالف المقترحة؛ عند
    التعارض **تستبعد اللاعب كله وتطبع التعارض** (لا تكتب فوق موجود).
  • تُزيل التكرار بين الصفوف.
  • للقراءة فقط: لا تكتب بالقاعدة ولا بـplayers_ar.csv.

⚠️ لا تتحقق من هوية اللاعب بالمصادر — هذا دور ملف المراجعة. ولا
   تُطبّق شيئاً: الكتابة خطوة منفصلة (أدناه).

التشغيل (من جذر المشروع، لأن المسار 'football.db' نسبي):
    python _archive/gen_translation_rows.py review.csv rows.json

الكتابة الفعلية بعد المخرجات (خطوات يدوية بالترتيب):
    1) git fetch؛ تأكد rev-list 0 0 (الـbot قد يدفع commit للقاعدة)
    2) ألحق الصفوف بنهاية players_ar.csv — بلا إعادة ترتيب الملف:
       سطر بصيغة  P#,,,,<player_en>,<player_ar>,<player_id>,<team_id>
       (CRLF، الأعمدة: priority,goals,league,team_ar,player_en,
        player_ar,player_id,team_id)
    3) انسخ football.db نسخة احتياطية خارج المشروع
    4) python apply_players_ar.py --check   ثم   python apply_players_ar.py
    5) قارن القاعدة بالنسخة الاحتياطية: كل سجل تغيّر يجب أن يكون
       (player_en, team_id) من الصفوف وكان فارغاً (أو 303519-نمط تصحيح
       مقصود)؛ أي سجل خارجها = إيقاف
    6) ولّد الصفحات (make_site3 → make_sitemap) ثم commit وpush
"""
import sqlite3,sys,csv,json
sys.stdout.reconfigure(encoding='utf-8')
src,out=sys.argv[1],sys.argv[2]
c=sqlite3.connect('file:football.db?mode=ro',uri=True)
rows=[r for r in csv.DictReader(open(src,encoding='utf-8-sig')) if r['confidence']=='high']
gen=[];conf=[];seen=set()
for r in rows:
    en,team,ar=r['name_en_db'],int(r['team_id']),r['name_ar_proposed']; pid=int(r['player_id']) if r['player_id'] else None
    var={(en,team):pid}
    if pid:
        for tb in ('lineup_players','player_stats'):
            for e,t,p in c.execute(f"select player_en,team_id,player_id from {tb} where player_id=? group by 1,2,3",(pid,)): var.setdefault((e,t),p)
    bad=False;cand=[]
    for (e,t),p in var.items():
        for tb in ('goals','events','lineup_players','player_stats'):
            for (x,) in c.execute(f"select distinct coalesce(player_ar,'') from {tb} where player_en=? and team_id=?"+(" and player_id=?" if (p and tb in('lineup_players','player_stats')) else ""),((e,t,p) if (p and tb in('lineup_players','player_stats')) else (e,t))):
                if x and x!=ar: bad=(tb,e,t,x)
        cand.append((e,t,p))
    if bad: conf.append((en,ar,bad)); continue
    for e,t,p in cand:
        k=(e,t,p or '')
        if k in seen: continue
        seen.add(k); gen.append((e,ar,p or '',t))
print('rows',len(gen),'players',len(rows),'conflicts',conf)
json.dump(gen,open(out,'w',encoding='utf-8'),ensure_ascii=False)
