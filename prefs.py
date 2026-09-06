#!/usr/bin/env python3
"""
طبقة تفضيلات مشتركة — localStorage
=====================================
مصدر واحد لقراءة/كتابة fbLeagues · fbClubs · fbSetup. أي صفحة
تحتاج التفضيلات تستورد prefs_script() بدل التعامل المباشر مع
localStorage — كانت نقطتان (onboard.py: wizard_script + render)،
وصارت أربعة مع الأونبوردنغ الجديد/شريط التنقّل/صفحة Following.

⚠️ **دالتان منفصلتان بقصد** — الشريط السفلي وحده موجود بـ22,403
   صفحة، وخريطة نادٍ←دوري (161 صفاً) مكلفة لو حُقنت بكل واحدة
   منها (~45 م.ب إضافية للموقع كله). `prefs_script()` خفيفة
   وبلا `conn`، تُحقن أينما احتيجت التفضيلات. `club_map_script(conn)`
   منفصلة تماماً، تُحقن **فقط** بالصفحات التي تستدعي فعلياً
   `cleanClubs()`.

⚠️ **الترتيب:** `wizard_script()`/أي مستهلك لـ`window.FBPrefs`
   يجب أن يُحقن **بعد** `prefs_script()`. `club_map_script()` لا
   يفرض ترتيباً بالنسبة لـ`prefs_script()` — `cleanClubs()` تفحص
   وجود `window.FBClubLeagueMap` وقت **الاستدعاء** لا وقت
   التعريف، فيكفي أن تسبق أي استدعاء فعلي لـ`cleanClubs()`.

⚠️ **فشل آمن:** لو `club_map_script()` غير مُحقَنة بالصفحة،
   `cleanClubs()` **لا تحذف شيئاً** — ترجع `getClubs()` كما هي
   بلا تعديل. غياب الخريطة يعني "لا تنظيف"، لا "امسح كل شيء".

الاستخدام:
    from prefs import prefs_script, club_map_script
    ... + prefs_script() + wizard_script(t) + ...          # أينما احتيجت التفضيلات
    ... + prefs_script() + club_map_script(conn) + ... + wizard_script(t) + ...  # + cleanClubs()
"""


def prefs_script():
    """
    كتلة JS خفيفة (window.FBPrefs) — بلا `conn`، بلا خريطة. آمنة
    للحقن بأي عدد صفحات (الشريط السفلي مرشَّح لاحقاً لكل الموقع).
    """
    return """<script>
window.FBPrefs = (function(){
  var K = {l:'fbLeagues', c:'fbClubs', s:'fbSetup'};

  function get(k, d) {
    try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; }
    catch(e) { return d; }
  }
  function set(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch(e) {}
  }

  function getLeagues() { return get(K.l, []); }
  function setLeagues(arr) { set(K.l, arr); }

  function getClubs() { return get(K.c, []); }
  function setClubs(arr) { set(K.c, arr); }

  function isSetupDone() { return !!get(K.s, null); }
  function markSetupDone() { set(K.s, '1'); }

  // يزيل من fbClubs أي نادٍ دوريه غير موجود بـfbLeagues.
  // ⚠️ fbLeagues فاضية = كل الدوريات ضمنياً (سلوك onboard.py
  //    الحالي) — لا يُحذف شيء وقتها.
  // ⚠️ الخريطة (window.FBClubLeagueMap) من club_map_script()
  //    منفصلة وقد تكون غائبة عن هذه الصفحة — غيابها = لا تنظيف
  //    (فشل آمن)، لا حذف كل شيء.
  function cleanClubs() {
    var map = window.FBClubLeagueMap;
    if (!map) return getClubs();
    var leagues = getLeagues();
    if (!leagues.length) return getClubs();
    var kept = getClubs().filter(function(tid){
      var lg = map[String(tid)];
      return !lg || leagues.indexOf(lg) >= 0;
    });
    setClubs(kept);
    return kept;
  }

  return {
    getLeagues: getLeagues, setLeagues: setLeagues,
    getClubs: getClubs, setClubs: setClubs,
    isSetupDone: isSetupDone, markSetupDone: markSetupDone,
    cleanClubs: cleanClubs
  };
})();
</script>"""


def club_map_script(conn):
    """
    خريطة نادٍ←دوري وحدها (window.FBClubLeagueMap) — من `teams`
    مباشرة. تُحقن فقط بالصفحات التي تستدعي `cleanClubs()` فعلياً،
    لا بكل صفحة تستورد `prefs_script()`.
    """
    rows = conn.execute("SELECT team_id, league_code FROM teams").fetchall()
    club_map = "{" + ",".join(
        f'"{r["team_id"]}":"{r["league_code"]}"' for r in rows) + "}"
    return f"<script>window.FBClubLeagueMap = {club_map};</script>"
