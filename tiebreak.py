#!/usr/bin/env python3
"""
ترتيب الفرق المتساوية — المواجهات المباشرة
=============================================
وحدة مستقلة. لا تشغّلها لحالها — `make_site3.py` بيستوردها.

المشكلة اللي بتحلها:
معظم الدوريات ما بترتّب المتساويين بفارق الأهداف الكلي مباشرة،
بل بالمواجهات المباشرة بينهم أولاً. فارق الأهداف الكلي بيجي بعدين.

مثال مؤكد (السعودي 2025-26):
  الفتح  37 نقطة  فارق -14
  الخليج 37 نقطة  فارق -8
الرسمي بيحط الفتح 11 والخليج 12 — رغم إن فارق الخليج أفضل.
السبب: المواجهات المباشرة بينهم.

⚠️ التطبيق حالياً على السعودي فقط. الأردني والعراقي معطّلين
   بسبب أمور تقنية موثّقة بالـREADME:
   - الأردني: نظام 3 مراحل، عدد المواجهات بين الفرق قد يختلف
   - العراقي: القاعدة تشترط اكتمال كل المواجهات، والموسم غير مكتمل
   لتفعيل أي منهما: غيّر القيمة في H2H_ENABLED إلى True بعد التحقق.
"""

# ------------------------------------------------------------------
# أي دوري يطبّق المواجهات المباشرة
# ------------------------------------------------------------------
H2H_ENABLED = {
    "SAU": True,    # [مؤكد] — تحقق خارجي: الفتح فوق الخليج رغم فارق أسوأ
    "JOR": False,   # نظام 3 مراحل — يحتاج تحقق قبل التفعيل
    "IRQ": True,    # [مؤكد] 2023 و2024 و2025 مكتملة ومتحقَّقة — 38 مباراة لكل نادٍ
}


def h2h_stats(conn, code, season, team_ids):
    """
    بيحسب نقاط وأهداف المواجهات بين مجموعة فرق محددة.
    بيرجع: {team_id: {"pts": n, "gf": n, "ga": n}}
    """
    stats = {t: {"pts": 0, "gf": 0, "ga": 0} for t in team_ids}
    ids = set(team_ids)

    rows = conn.execute("""
        SELECT home_id, away_id, home_goals, away_goals
        FROM matches
        WHERE league_code = ? AND season = ?
    """, (code, season)).fetchall()

    for r in rows:
        h, a = r["home_id"], r["away_id"]
        if h not in ids or a not in ids:
            continue
        hg, ag = r["home_goals"], r["away_goals"]
        if hg is None or ag is None:
            continue

        stats[h]["gf"] += hg
        stats[h]["ga"] += ag
        stats[a]["gf"] += ag
        stats[a]["ga"] += hg

        if hg > ag:
            stats[h]["pts"] += 3
        elif hg < ag:
            stats[a]["pts"] += 3
        else:
            stats[h]["pts"] += 1
            stats[a]["pts"] += 1

    return stats


def sort_table(conn, code, season, rows):
    """
    بياخد صفوف الجدول (من get_data) وبيرجعها مرتّبة.

    المستوى الأول دائماً: النقاط.
    عند التساوي:
      - لو الدوري مفعّل بـH2H: نقاط المواجهات، فارق المواجهات،
        أهداف المواجهات، ثم الفارق الكلي، ثم الأهداف الكلية
      - غير هيك: الفارق الكلي، ثم الأهداف الكلية

    rows لازم تحتوي: team_id, points, diff, scored
    """
    use_h2h = H2H_ENABLED.get(code, False)

    # نجمّع الصفوف حسب النقاط
    groups = {}
    for r in rows:
        groups.setdefault(r["points"], []).append(r)

    result = []

    for pts in sorted(groups, reverse=True):
        group = groups[pts]

        if len(group) == 1 or not use_h2h:
            # مجموعة من فريق واحد، أو دوري غير مفعّل — الفارق الكلي
            group = sorted(group,
                           key=lambda r: (-r["diff"], -r["scored"]))
            result.extend(group)
            continue

        # مجموعة متساوية بالنقاط ودوري مفعّل — نحسب المواجهات
        ids = [r["team_id"] for r in group]
        st = h2h_stats(conn, code, season, ids)

        group = sorted(group, key=lambda r: (
            -st[r["team_id"]]["pts"],                              # 1
            -(st[r["team_id"]]["gf"] - st[r["team_id"]]["ga"]),    # 2
            -st[r["team_id"]]["gf"],                               # 3
            -r["diff"],                                            # 4
            -r["scored"],                                          # 5
        ))
        result.extend(group)

    return result
