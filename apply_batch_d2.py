import csv, io, re, unicodedata

FILL = {
"Hazzaa Al Ghamdi": "هزاع الغامدي",
"Fawaz Al Sqoor": "فواز الصقور",
"Ali Al Bulaihi": "علي البليهي",
"Abdullah Al Malki": "عبد الله المالكي",
"Yasser Al Shahrani": "ياسر الشهراني",
"Ahmed Bamsaud": "أحمد بامسعود",
"Firas Al Buraikan": "فراس البريكان",
"Hassan Kadesh": "حسن كادش",
"Mohammed Kanno": "محمد كنو",
"Sami Al Najei": "سامي النجعي",
"Ahmed Al Ghamdi": "أحمد الغامدي",
"Hattan Bahebri": "هتان باهبري",
"Sultan Al Otaibi": "سلطان العتيبي",
"Abdulaziz Al Aliwa": "عبد العزيز العليوة",
"Abdulelah Al Amri": "عبد الإله العمري",
"Mohammed Al Breik": "محمد البريك",
"Nawaf Al Habashi": "نواف الحبشي",
"Riyad Sharahili": "رياض شراحيلي",
"Abdullah Al Hamdan": "عبد الله الحمدان",
"Ali Hazazi": "علي هزازي",
"Fawaz Al Sqour": "فواز الصقور",
"Rakan Al Najjar": "راكان النجار",
"Yahya Al Salem": "يحيى السالم",
# صيغ كاملة ظهرت بالفئة D وتحتاج نفس الترجمة
"Hazzaa Ahmed Al Ghamdi": "هزاع الغامدي",
"Mohamed Kanno": "محمد كنو",
"Nawaf Al-Habashi": "نواف الحبشي",
"Abdullah Al-Hamdan": "عبد الله الحمدان",
"Abdulaziz Al-Aliwa": "عبد العزيز العليوة",
"Abdulelah Al Malki": "عبد الإله المالكي",
"Riyadh Sharahili": "رياض شراحيلي",
"Rakan Najjar": "راكان النجار",
}


def fold(s):
    """بصمة مرنة: تجريد اللكنات وتوحيد الشرطة والمسافة"""
    s = unicodedata.normalize("NFKD", (s or "").strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"[-.]", " ", s)
    return " ".join(s.split()).lower()


rows = list(csv.DictReader(io.open("players_ar.csv", encoding="utf-8-sig")))

# خريطة مرنة من البصمة للترجمة
folded = {fold(k): v for k, v in FILL.items()}

n = skipped = 0
matched = set()
for r in rows:
    en = r["player_en"]
    key = fold(en)
    if key in folded:
        matched.add(key)
        if (r["player_ar"] or "").strip():
            skipped += 1
            continue
        r["player_ar"] = folded[key]
        n += 1

missing = [k for k, f in ((k, fold(k)) for k in FILL)
           if f not in matched]

with io.open("players_ar.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["priority", "goals", "league",
                                      "team_ar", "player_en",
                                      "player_ar"])
    w.writeheader()
    w.writerows(rows)

d = [r for r in rows if r["priority"] == "D"]
done_d = sum(1 for r in d if (r["player_ar"] or "").strip())
total_done = sum(1 for r in rows if (r["player_ar"] or "").strip())

print(f"أُضيف: {n}  |  مترجَم أصلاً: {skipped}")
if missing:
    print(f"\nلم يُوجد إطلاقاً: {len(missing)}")
    for m in missing:
        print("   ", m)
print(f"\nالفئة D: {done_d} من {len(d)}")
print(f"الإجمالي المترجَم: {total_done} من {len(rows)}")
