/*
 * liveTable — الترتيب المباشر (12 أكتوبر 2026)
 * ================================================
 * مصدر JS مستقل (بلا DOM ولا fetch) يحسب جدول الدوري بنتائج المباريات الجارية والمنتهية للتو فوق لقطة
 * الجدول الثابت. نفس قواعد `tiebreak.sort_table` حرفياً لكل دوري. لا يُحقن بأي صفحة بعد (مرحلة 2 محلية)،
 * وسيُضمَّن لاحقاً بحزمة /assets عبر make_assets.py.
 *
 * الاستعمال:
 *   const res = liveTable(snapshot, m, f);   // m, f من ردّ الـworker: {m:{id:{h,a,e,s,th,ta,lg}}, f:{id:{h,a,s,th,ta,lg,ft}}}
 *   res === null                  → الميزة مطفأة لهذا الدوري (JOR) أو اللقطة ناقصة: اعرض الجدول الثابت
 *   res = { rows, live, addedF, addedLive }
 *     rows[i] = { team_id, pos, base_pos, played, wins, draws, losses, scored, diff, points, live }
 *
 * لقطة الجدول (snapshot) — يولّدها المولِّد وقت البناء:
 *   {
 *     league: "SAU", season: 2026,
 *     rules:  { enabled: true, leagueId: 307, h2h: true, twoOnly: false },   // من tiebreak.H2H_ENABLED / H2H_TWO_TEAM_ONLY + config
 *     counted_ids: [match ids المحسوبة بالجدول],
 *     rows:    [ { team_id, played, wins, draws, losses, scored, diff, points } … ]   // بترتيب get_table النهائي
 *     matches: [ [id, home, away, hg, ag] … ]    // نفس المباريات المحسوبة بالجدول (لكسر التعادل بالمواجهات)
 *     alias:   { "<providerTeamId>": <ourTeamId> }   // الأندية المدموجة
 *   }
 *
 * ⚠️ المنطق:
 *   - نتيجة `f` تُضاف فقط إن كان id غير موجود بـ counted_ids (وإلا الجدول الثابت أعاد البناء وعدّها)، وبحالة FT/AET/PEN فقط،
 *     وبـlg/th/ta (الـworker القديم بلا هذه الحقول → تُتجاهل)، ولا تُضاف مرتين لنفس id.
 *   - المباراة الجارية `m` تُضاف بنتيجتها الحالية (null = 0) إن كانت lg دوري اللقطة، وليست بـcounted_ids ولا مضافة من f.
 *   - الترتيب: النقاط ثم: (نقاط المواجهات، فارق المواجهات، أهداف المواجهات، الفارق الكلي، الأهداف الكلية) لدوري مفعّل H2H،
 *     وإلا (الفارق الكلي، الأهداف الكلية). دوري twoOnly (المغرب): المواجهات لتعادل فريقين بالضبط فقط.
 *     الفرز مستقر: المتساوون كلياً يبقون بترتيب الإدخال (= ترتيب get_table) كما بـsorted() بايثون.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.liveTable = factory();
})(typeof self !== "undefined" ? self : this, function () {
  var FINAL = { FT: 1, AET: 1, PEN: 1 };

  function num(x) { return typeof x === "number" && isFinite(x) ? x : 0; }

  // مواجهات مجموعة فرق: نفس h2h_stats بالبايثون (على كل المباريات المحسوبة + المضافة)
  function h2hStats(pool, ids) {
    var st = {}, set = {};
    ids.forEach(function (t) { st[t] = { pts: 0, gf: 0, ga: 0 }; set[t] = true; });
    pool.forEach(function (x) {
      var h = x[1], a = x[2], hg = x[3], ag = x[4];
      if (!set[h] || !set[a]) return;
      st[h].gf += hg; st[h].ga += ag;
      st[a].gf += ag; st[a].ga += hg;
      if (hg > ag) st[h].pts += 3;
      else if (hg < ag) st[a].pts += 3;
      else { st[h].pts += 1; st[a].pts += 1; }
    });
    return st;
  }

  // مطابق لـtiebreak.sort_table
  function sortRows(rows, rules, pool) {
    var useH2h = !!rules.h2h, two = !!rules.twoOnly;
    var groups = {}, order = [];
    rows.forEach(function (r) {
      if (!(r.points in groups)) { groups[r.points] = []; order.push(r.points); }
      groups[r.points].push(r);
    });
    order.sort(function (a, b) { return b - a; });
    var out = [];
    order.forEach(function (pts) {
      var g = groups[pts];
      var skip = g.length === 1 || !useH2h || (two && g.length > 2);
      if (skip) {
        g = g.slice().sort(function (x, y) { return (y.diff - x.diff) || (y.scored - x.scored); });
      } else {
        var st = h2hStats(pool, g.map(function (r) { return r.team_id; }));
        g = g.slice().sort(function (x, y) {
          var a = st[x.team_id], b = st[y.team_id];
          return (b.pts - a.pts) || ((b.gf - b.ga) - (a.gf - a.ga)) || (b.gf - a.gf) ||
                 (y.diff - x.diff) || (y.scored - x.scored);
        });
      }
      out = out.concat(g);
    });
    return out;
  }

  function liveTable(snap, m, f) {
    if (!snap || !snap.rules || !snap.rules.enabled || !Array.isArray(snap.rows)) return null;
    var rules = snap.rules, alias = snap.alias || {};
    var canon = function (id) { return alias[id] != null ? alias[id] : id; };

    var counted = {};
    (snap.counted_ids || []).forEach(function (id) { counted[String(id)] = true; });

    var byTeam = {}, rows = snap.rows.map(function (r) {
      var c = {
        team_id: r.team_id, played: r.played, wins: r.wins, draws: r.draws, losses: r.losses,
        scored: r.scored, diff: r.diff, points: r.points, live: false
      };
      byTeam[c.team_id] = c;
      return c;
    });
    var basePos = {};
    rows.forEach(function (r, i) { basePos[r.team_id] = i + 1; });

    var pool = (snap.matches || []).map(function (x) { return x.slice(); });
    var seen = {};
    var addedF = 0, addedLive = 0;

    function row(tid) {
      if (!byTeam[tid]) {   // فريق بلا مباراة منتهية بعد (بداية موسم): صف أصفار
        var r = { team_id: tid, played: 0, wins: 0, draws: 0, losses: 0, scored: 0, diff: 0, points: 0, live: false };
        byTeam[tid] = r; rows.push(r); basePos[tid] = rows.length;
      }
      return byTeam[tid];
    }
    function apply(id, th, ta, hg, ag, live) {
      var H = row(canon(th)), A = row(canon(ta));
      H.played++; A.played++;
      H.scored += hg; A.scored += ag;
      H.diff += hg - ag; A.diff -= hg - ag;
      if (hg > ag) { H.wins++; H.points += 3; A.losses++; }
      else if (hg < ag) { A.wins++; A.points += 3; H.losses++; }
      else { H.draws++; A.draws++; H.points++; A.points++; }
      if (live) { H.live = true; A.live = true; }
      pool.push([id, canon(th), canon(ta), hg, ag]);
    }

    // f: نتائج انتهت للتو ولم يحسبها الجدول الثابت بعد
    Object.keys(f || {}).forEach(function (id) {
      var e = f[id];
      if (!e || !FINAL[e.s] || counted[id] || seen[id]) return;
      if (e.lg !== rules.leagueId || e.th == null || e.ta == null) return;
      if (typeof e.h !== "number" || typeof e.a !== "number") return;
      seen[id] = true; addedF++;
      apply(id, e.th, e.ta, e.h, e.a, false);
    });
    // m: المباريات الجارية بنتيجتها الحالية
    Object.keys(m || {}).forEach(function (id) {
      var e = m[id];
      if (!e || counted[id] || seen[id]) return;
      if (e.lg !== rules.leagueId || e.th == null || e.ta == null) return;
      seen[id] = true; addedLive++;
      apply(id, e.th, e.ta, num(e.h), num(e.a), true);
    });

    // (30 أكتوبر 2026) لا جارية ولا منتهية للتو = ترتيب اللقطة حرفياً (get_table — صار ترتيب المزوّد متى طابقنا، tiebreak.provider_order):
    //   إعادة الفرز بقواعدنا هنا كانت تقلب متعادلَين رتّبهما المزوّد بلا أي نتيجة جديدة. أثناء المباريات: حسابنا (قرار عمرو)
    var sorted = (addedF || addedLive) ? sortRows(rows, rules, pool) : rows.slice();
    sorted.forEach(function (r, i) { r.pos = i + 1; r.base_pos = basePos[r.team_id]; });
    return { rows: sorted, live: addedLive > 0, addedF: addedF, addedLive: addedLive };
  }

  liveTable.sortRows = sortRows;
  return liveTable;
});
