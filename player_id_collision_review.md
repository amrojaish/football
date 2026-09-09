# مراجعة تصادم player_id — بند 27 (فرع بحثي)

مدخل لمراجعة بشرية، **ليس حلاً ولا تصنيفاً نهائياً**. كل صف يعني:
نفس `player_id` بالديتابيس مربوط بصيغتَي اسم مختلفتين نصياً
(نسبة تشابه < 0.5، بمعيار متماثل الاتجاه) **وبصفر نادٍ مشترك**
بين فترتيهما — لا دليل قاطع على شخصين حقيقيين، فقط أولوية
مراجعة أعلى من البقية.

⚠️ **قيد معروف**: ألقاب الشهرة الشائعة بالكرة المصرية/العربية
(`Zizo`، `Meme`، `Kabaka`، `Beckham`، `Body`...) ستظهر هنا
كإيجابيات كاذبة محتملة — لاعب واحد بلقبه مقابل اسمه الرسمي،
لا شخصان. لا تنقية نصية تميّز هذا؛ يحتاج عيناً بشرية بالسياق
(انتقال نادٍ حقيقي مع تغيير اسم حقيقي يبدو مطابقاً بنفس
الأرقام للقب محلي يظهر بنادٍ آخر — التمييز صعب آلياً بقصد).

**إجمالي `player_id` بأكثر من صيغة اسم (الجامع الخام، بند 27): 2,554**
**مرشّحون بهذا المعيار: 43 (1.7%)**

مصدر الفحص: `lineup_players` + `player_stats` (الجدولان الوحيدان
الحاملان `player_id`)، مقروءة بوضع `mode=ro` — صفر كتابة على
`football.db`. المعيار: `difflib.SequenceMatcher` بأعلى قيمة من
كلا الاتجاهين — ⚠️ الاتجاه الواحد غير متماثل رياضياً (اكتُشف
أثناء بناء هذا الملف: نفس الزوج أعطى 0.42 باتجاه و0.53 بالعكس،
صحَّح فرقاً بين عدّ أول 44 وعدّ نهائي مستقر 43).

| player_id | الصيغة أ | فترتها | نادي أ | الصيغة ب | فترتها | نادي ب | تشابه |
|---|---|---|---|---|---|---|---|
| 53894 | Meme | 2025-08-16..2026-05-16 (UAE) | Dibba Al-Fujairah | Mohanad Ali | 2022-08-02..2022-08-10 (QAT) | Al-Sailiya | 0.13 |
| 295633 | Oufa | 2025-08-10..2026-08-31 (EGY) | National Bank of Egypt | Ahmed Amin | 2023-06-01..2023-07-15 (EGY) | Sharkia Enppi | 0.14 |
| 17096 | Body | 2025-08-08..2026-04-19 (EGY) | Al Ittihad | Abdel Rahman Ramadan | 2022-10-23..2025-03-05 (EGY) | Ceramica Cleopatra | 0.17 |
| 42305 | Saeed Alhaj | 2022-08-02..2023-05-08 (QAT) | Al-Sailiya | S. E. Eisa | 2026-05-08..2026-05-08 (QAT) | Al Kharaitiyat | 0.19 |
| 17143 | Beckham | 2026-08-28..2026-09-02 (EGY) | Ceramica Cleopatra | A. Ramadan | 2025-08-15..2026-05-20 (EGY) | Al Ahly | 0.24 |
| 428224 | Kabaka | 2025-08-09..2026-05-03 (EGY) | ZED FC | Ahmed Gomma | 2023-07-26..2025-02-21 (EGY) | Al Ahly, Modern Sport FC | 0.24 |
| 283564 | O. Fathy | 2026-08-23..2026-09-01 (EGY) | Olympic El Qanah | Ossama El Nagar | 2024-05-11..2025-05-29 (EGY) | El Mokawloon, Ghazl El Mehalla | 0.26 |
| 42036 | Bahaa Ellithi | 2022-08-01..2025-04-18 (QAT) | Al Sadd, Al Ahli Doha, Muaither SC | B. Mamdouh | 2025-08-14..2026-05-08 (QAT) | Al Shahaniya, Al-Rayyan SC | 0.26 |
| 17226 | M. Dowidar | 2025-08-10..2026-08-31 (EGY) | National Bank of Egypt | Mostafa Adel | 2022-10-19..2025-05-16 (EGY) | Sharkia Enppi | 0.27 |
| 310083 | M. Shehata | 2026-08-21..2026-09-02 (EGY) | Abu Qair Semad | Mostafa Abdelrahim | 2024-12-01..2025-05-28 (EGY) | National Bank of Egypt | 0.29 |
| 17187 | M. Shalaby | 2025-08-10..2026-08-26 (EGY) | National Bank of Egypt | Karim Tarek | 2022-10-20..2026-09-07 (EGY) | El Geish | 0.29 |
| 384483 | A. Nader | 2026-01-22..2026-01-22 (EGY) | El Mokawloon | Ahmed Hawash | 2022-10-29..2025-03-04 (EGY) | Sharkia Enppi | 0.3 |
| 42139 | F. Younes | 2025-08-14..2026-08-29 (QAT) | Al-Sailiya, Al-Duhail SC | Fahad Baker | 2022-08-03..2025-04-18 (QAT) | Al-Rayyan SC | 0.3 |
| 42035 | R. Suhail | 2025-08-15..2026-01-29 (QAT) | UMM Salal | Rami Al Hamwende | 2023-08-27..2025-04-18 (QAT) | Al-Arabi SC | 0.32 |
| 282597 | A. Reyed | 2025-08-14..2026-08-28 (QAT) | Al Ahli Doha | Ahmed Mawla | 2024-08-09..2024-08-09 (QAT) | Al-Khor | 0.32 |
| 562540 | Zizo | 2025-10-05..2026-09-01 (EGY) | Wadi Degla | Z. Osama | 2025-09-20..2026-05-15 (UAE) | Al Nasr | 0.33 |
| 437725 | O. Noureddine | 2024-08-24..2025-05-25 (UAE) | Khorfakkan | N. Oussama | 2023-08-30..2024-06-14 (MAR) | Chabab Mohammédia | 0.35 |
| 326793 | N. Hermann | 2024-03-30..2024-04-07 (UAE) | Al-Jazira | H. Behiratche | 2023-02-14..2023-04-18 (UAE) | Al-Dhafra | 0.35 |
| 335018 | F. Said | 2025-09-26..2026-04-27 (QAT) | UMM Salal | Fares Amer | 2023-08-18..2024-03-15 (QAT) | Al-Duhail SC | 0.35 |
| 101647 | A. Fawzi | 2025-08-17..2026-02-07 (UAE) | Baniyas SC | Ahmad Fawzi Johar Faraj Abdalla | 2024-05-05..2025-03-28 (UAE) | Al-Jazira | 0.36 |
| 17062 | H. Balaha | 2025-08-08..2026-05-20 (EGY) | Smouha SC, Al Ittihad | Hesham Nabawi | 2022-12-01..2022-12-12 (EGY) | Modern Sport FC | 0.36 |
| 197965 | A. Mohammed | 2025-08-14..2026-08-27 (QAT) | Al Shamal | Ali Ghulais | 2023-10-20..2024-04-24 (QAT) | Muaither SC | 0.36 |
| 135952 | S. Al Mesmari | 2026-08-16..2026-08-30 (UAE) | Hatta SC | A. Saeed | 2025-11-21..2026-01-08 (UAE) | Dibba Al-Fujairah | 0.38 |
| 320199 | R. Al Menhali | 2025-08-16..2026-05-16 (UAE) | Shabab Al Ahli Dubai | Rakaan Waleed | 2022-10-15..2023-05-11 (UAE) | Al-Jazira | 0.38 |
| 533871 | A. Al Rashidi | 2026-08-21..2026-08-27 (QAT) | Al-Gharafa | A. Fayez | 2025-08-15..2026-04-27 (QAT) | UMM Salal | 0.38 |
| 2702 | Munir | 2025-10-05..2026-05-24 (MAR) | Renaissance Berkane | Monir El Kajoui | 2023-09-22..2024-03-14 (SAU) | Al-Wehda | 0.4 |
| 242795 | F. Saleh | 2025-09-19..2026-05-16 (UAE) | Al-Dhafra | Feras Al Khaseebi | 2024-08-24..2025-01-23 (UAE) | Dibba Al Hisn | 0.4 |
| 498397 | Bencharki | 2026-08-21..2026-08-31 (EGY) | National Bank of Egypt | Mohamed Ashraf Ben Sharqi | 2025-01-15..2025-05-29 (EGY) | Ghazl El Mehalla | 0.41 |
| 393210 | Otta | 2026-08-27..2026-08-31 (EGY) | Pyramids FC | Ahmed Atef Otta | 2022-10-20..2024-06-27 (EGY) | El Mokawloon, ZED FC | 0.42 |
| 452385 | A. Hamad | 2025-08-17..2026-08-30 (UAE) | Al Wahda FC | Hamad Al Menhali | 2023-12-15..2024-04-07 (UAE) | Al-Jazira | 0.42 |
| 283324 | S. Adil | 2025-10-17..2026-08-28 (UAE) | Shabab Al Ahli Dubai | Sultan Adill Alamiri | 2022-09-02..2023-08-18 (UAE) | Al-Ittihad Kalba | 0.44 |
| 284150 | Mouaz Gadelseed Abdalla | 2022-08-01..2024-04-24 (QAT) | Al Sadd, Al-Rayyan SC | Mouz Jaad | 2025-11-08..2026-04-27 (QAT) | Al-Sailiya | 0.44 |
| 283330 | Adham Hegazy | 2024-08-24..2025-05-24 (UAE) | Baniyas SC | Adham Khalid Ali Abdelhameed | 2026-09-05..2026-09-05 (UAE) | Hatta SC | 0.45 |
| 283174 | Mohamed Naceur Al Manai | 2023-03-18..2023-05-09 (QAT) | Al-Markhiya | M. Manai | 2026-08-22..2026-08-28 (QAT) | Al Sadd | 0.45 |
| 498461 | M. Said | 2026-03-22..2026-09-01 (EGY) | Wadi Degla, Kahraba Ismailia | Mohamed Saied Zeeka | 2025-01-28..2025-05-02 (EGY) | Smouha SC | 0.46 |
| 42216 | Ibrahim Nasser Kala | 2022-08-02..2025-04-05 (QAT) | Al-Khor, Al-Arabi SC | I. Kala | 2025-11-23..2025-11-23 (QAT) | Al Shahaniya | 0.46 |
| 343176 | Y. Nader | 2026-05-29..2026-05-29 (EGY) | Al Ittihad | Youssef Nader Elshazly | 2023-06-28..2025-02-23 (EGY) | Pyramids FC | 0.47 |
| 42147 | I. Masoud | 2025-08-16..2026-04-27 (QAT) | Qatar SC | Ibrahim Abdelhalim Masoud | 2022-08-03..2023-05-08 (QAT) | Al-Rayyan SC | 0.47 |
| 146807 | K. Kbiri | 2023-08-26..2025-05-11 (MAR) | Olympique Safi | K. Alaoui | 2025-09-13..2026-06-28 (MAR) | Raja Casablanca | 0.47 |
| 342746 | M. Hamdy | 2025-08-08..2026-08-31 (EGY) | AL Masry | Mohamed Tarek | 2023-01-03..2026-05-20 (EGY) | Ceramica Cleopatra, Modern Sport FC | 0.48 |
| 458144 | A. Ramadan | 2026-08-22..2026-08-22 (EGY) | Suez Petrojet | Abdel Rahman Hamawy | 2024-02-20..2024-08-18 (EGY) | El Dakhleya | 0.48 |
| 456963 | A. Bostangy | 2026-03-11..2026-05-21 (EGY) | ZED FC | Abdallah Boustenji | 2025-05-29..2025-05-29 (EGY) | Smouha SC | 0.48 |
| 417820 | A. Maâli | 2023-10-07..2025-05-11 (MAR) | Ittihad Tanger | Abdel Hamid Maali | 2025-08-08..2025-11-02 (EGY) | Zamalek SC | 0.48 |

---
راجع أيضاً: بند 27 بـ`README.md` (إعادة التصنيف الجذرية 9 سبتمبر)
لسياق القرار الكامل — لا دمج آلي بأي مستوى ثقة، هذا الملف
مدخل مراجعة لا أكثر.
