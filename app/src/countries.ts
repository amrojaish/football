// Country names + aliases for competition search (15 Nov 2026). Same data as saffara.app/search.html (LGS: ca, ce, x).
// Key = our country/league code; a domestic cup's code starts with it (SAU-KC, JOR-SH...). Continental cups have none.
export const COUNTRIES: Record<string, { ar: string; en: string; aliases: string[] }> = {
  JOR: { ar: 'الأردن', en: 'Jordan', aliases: [] },
  IRQ: { ar: 'العراق', en: 'Iraq', aliases: [] },
  SAU: { ar: 'السعودية', en: 'Saudi Arabia', aliases: ['KSA', 'Saudi'] },
  EGY: { ar: 'مصر', en: 'Egypt', aliases: ['Misr'] },
  UAE: { ar: 'الإمارات', en: 'United Arab Emirates', aliases: ['UAE', 'Emirates', 'امارات'] },
  QAT: { ar: 'قطر', en: 'Qatar', aliases: [] },
  MAR: { ar: 'المغرب', en: 'Morocco', aliases: [] },
  TUN: { ar: 'تونس', en: 'Tunisia', aliases: [] },
  ALG: { ar: 'الجزائر', en: 'Algeria', aliases: [] },
  KUW: { ar: 'الكويت', en: 'Kuwait', aliases: [] },
};

// Country code of a competition: the league code itself, or the prefix of a domestic cup code; '' for continental cups
export function countryOf(code: string) {
  const c = code.split('-')[0];
  return COUNTRIES[c] ? c : '';
}

// All search keys for a competition's country: Arabic, English, aliases and the code (JOR, SAU...)
export function countryKeys(code: string): string[] {
  const c = countryOf(code);
  if (!c) return [];
  const x = COUNTRIES[c];
  return [x.ar, x.en, c, ...x.aliases];
}
