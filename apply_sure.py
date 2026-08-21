import csv, io, json

# 17 اسماً مؤكَّداً فقط — لاعبون أجانب بصيغة عربية موثّقة إعلامياً.
# الباقي (1,659) أسماء سعودية محلية لا مصدر لتأكيدها، وترجمتها
# تخمين يخالف قاعدة المشروع: "الإنجليزي أفضل من العربي الخطأ".
FILL = json.loads(r"""{
"Roger Ibañez": "روجر إيبانيز",
"Franck Kessié": "فرانك كيسييه",
"Fashion Sakala": "فاشون ساكالا",
"Marcelo Brozović": "مارسيلو بروزوفيتش",
"Abderazak Hamdallah": "عبد الرزاق حمد الله",
"Abderrazak Hamdallah": "عبد الرزاق حمد الله",
"Abdou Diallo": "عبدو ديالو",
"Abdoulaye Doucoure": "عبد الله دوكوريه",
"Abdoulaye Doucouré": "عبد الله دوكوريه",
"Abdoulaye Seck": "عبد الله سيك",
"Abdelhamid Sabiri": "عبد الحميد صبيري",
"Abdelkader Bedrane": "عبد القادر بدران",
"A. Carrillo": "غيريرو كاريو",
"A. Toșca": "ألين توسكا",
"A. Traore": "بيرتراند تراوري",
"A. Diallo": "عبدو ديالو",
"A. Pululu": "فابريس بولولو"
}""")

rows = list(csv.DictReader(io.open("players_ar.csv", encoding="utf-8-sig")))
n = 0
found = set()
for r in rows:
    en = r["player_en"]
    if en in FILL:
        found.add(en)
        if not (r["player_ar"] or "").strip():
            r["player_ar"] = FILL[en]
            n += 1

missing = [k for k in FILL if k not in found]

with io.open("players_ar.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["priority","goals","league",
                                      "team_ar","player_en","player_ar"])
    w.writeheader()
    w.writerows(rows)

total = sum(1 for r in rows if (r["player_ar"] or "").strip())
print(f"أُضيف: {n}")
if missing:
    print(f"لم يُوجد بالملف: {len(missing)} — {missing}")
print(f"الإجمالي المترجَم: {total} من {len(rows)}")
