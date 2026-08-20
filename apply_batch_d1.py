import csv, io

FILL = {
"Saeed Baattia": "سعيد باعطية",
"Eid Al Muwallad": "عيد المولد",
"Pedro Rebocho": "بيدرو ريبوشو",
"Abdulelah Al Khaibari": "عبد الإله الخيبري",
"Mailson": "مايلسون",
"Abdulquddus Atiah": "عبد القدوس عطية",
"Fahad Al Abdulrazzaq": "فهد العبدالرزاق",
"Bandar Nasser": "بندر ناصر",
"Fahad Al Rashidi": "فهد الرشيدي",
"Hazzaa Al Ghamdi": "هزاع الغامدي",
"Mohammed Al Fuhaid": "محمد الفهيد",
"Mansor Al Beshe": "منصور البيشي",
"Nawaf Al Saadi": "نواف السعدي",
"Paulo Vítor": "باولو فيتور",
"Qassem Lajami": "قاسم لاجامي",
"K. Casteels": "كوين كاستيلس",
"Nader Al Sharari": "نادر الشراري",
"Abdulaziz Majrashi": "عبد العزيز مجرشي",
"Faisal Al Subiani": "فيصل السبياني",
"Fawaz Al Sqoor": "فواز الصقور",
"Marcelo Grohe": "مارسيلو جروهي",
"Amin Al Bukhari": "أمين البخاري",
"Rúben Neves": "روبن نيفيز",
"Mohammed Al Owais": "محمد العويس",
"Ali Al Bulaihi": "علي البليهي",
"Mohammed Al Yami": "محمد اليامي",
"Nawaf Al Aqidi": "نواف العقيدي",
"Sultan Al Ghannam": "سلطان الغنام",
"Abdullah Al Malki": "عبد الله المالكي",
"Ali Lajami": "علي لاجامي",
"Saud Abdulhamid": "سعود عبد الحميد",
"Yasser Al Shahrani": "ياسر الشهراني",
"Ahmed Bamsaud": "أحمد بامسعود",
"Ali Al Asmari": "علي الأسمري",
"Fahad Al Muwallad": "فهد المولد",
"Firas Al Buraikan": "فراس البريكان",
"Hassan Kadesh": "حسن كادش",
"Mohammed Kanno": "محمد كنو",
"Mukhtar Ali": "مختار علي",
"Nasser Al Dawsari": "ناصر الدوسري",
"Salem Al Dawsari": "سالم الدوسري",
"Sami Al Najei": "سامي النجعي",
"Abdullah Radif": "عبد الله رديف",
"Ahmed Al Ghamdi": "أحمد الغامدي",
"Ayman Yahya": "أيمن يحيى",
"Hattan Bahebri": "هتان باهبري",
"Khalid Al Ghannam": "خالد الغنام",
"Mohamed Simakan": "محمد سيماكان",
"Sultan Al Otaibi": "سلطان العتيبي",
"Turki Al Ammar": "تركي العمار",
"Abdulaziz Al Aliwa": "عبد العزيز العليوة",
"Abdulelah Al Amri": "عبد الإله العمري",
"Abdulrahman Ghareeb": "عبد الرحمن غريب",
"Ahmed Sharahili": "أحمد شراحيلي",
"Ali Majrashi": "علي مجرشي",
"Faisal Al Ghamdi": "فيصل الغامدي",
"Hamed Al Ghamdi": "حامد الغامدي",
"Khalifah Al Dawsari": "خليفة الدوسري",
"Meshari Al Nemer": "مشاري النمر",
"Mohammed Al Breik": "محمد البريك",
"Mohammed Al Kuwaykibi": "محمد الكويكبي",
"Mohammed Al Rubaie": "محمد الربيعي",
"Nawaf Al Habashi": "نواف الحبشي",
"Riyad Sharahili": "رياض شراحيلي",
"Saleh Al Shehri": "صالح الشهري",
"Sultan Mandash": "سلطان مندش",
"Abdullah Al Hamdan": "عبد الله الحمدان",
"Abdullah Al Khaibari": "عبد الله الخيبري",
"Ahmed Al Kassar": "أحمد الكسار",
"Ali Hazazi": "علي هزازي",
"Aymeric Laporte": "إيمريك لابورت",
"Fawaz Al Sqour": "فواز الصقور",
"Hamdan Al Shamrani": "حمدان الشمراني",
"Ibrahim Mahnashi": "إبراهيم محنشي",
"Khalid Al Subaie": "خالد السبيعي",
"Mohammed Al Saiari": "محمد الصياري",
"Mohammed Jahfali": "محمد جحفلي",
"Muteb Al Mufarrij": "متعب المفرج",
"Nawaf Boushal": "نواف بوشل",
"Rakan Al Najjar": "راكان النجار",
"Saad Al Nasser": "سعد الناصر",
"Saleh Al Amri": "صالح العمري",
"Yahya Al Salem": "يحيى السالم",
}

rows = list(csv.DictReader(io.open("players_ar.csv", encoding="utf-8-sig")))
n = skipped = 0
found = set()
for r in rows:
    en = r["player_en"]
    if en in FILL:
        found.add(en)
        if (r["player_ar"] or "").strip():
            skipped += 1
            continue
        r["player_ar"] = FILL[en]
        n += 1

missing = [k for k in FILL if k not in found]

with io.open("players_ar.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["priority","goals","league",
                                      "team_ar","player_en","player_ar"])
    w.writeheader()
    w.writerows(rows)

d = [r for r in rows if r["priority"] == "D"]
done_d = sum(1 for r in d if (r["player_ar"] or "").strip())
total_done = sum(1 for r in rows if (r["player_ar"] or "").strip())

print(f"أُضيف: {n}  |  مترجَم أصلاً: {skipped}")
if missing:
    print(f"\nلم يُوجد بالملف: {len(missing)}")
    for m in missing:
        print("   ", m)
print(f"\nالفئة D: {done_d} من {len(d)}")
print(f"الإجمالي المترجَم: {total_done} من {len(rows)}")
