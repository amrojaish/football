// Shared data access for the app (api/v1 static JSON + the saffara-live worker).
export const SITE = 'https://saffara.app';
export const API = SITE + '/api/v1';
export const LIVE = 'https://saffara-live.abujaishamr.workers.dev';
export const LIVE_EVERY_MS = 30_000;

export type Name = { ar: string; en: string };
export type Team = { name: Name; short?: Name; logo?: string };
export type Teams = Record<string, Team>;
export type Score = { h: number; a: number };
export type DayMatch = {
  id: number; league: string; kickoff: string; status: string;
  home: number; away: number; score?: Score; pen?: Score;
};
export type Comp = { code: string; name: Name; logo?: string; type?: string; season?: number; label?: string };
export type Live = { h?: number; a?: number; e?: number; s?: string };

export type Person = { id?: number; name: Name; short?: Name };
export type MatchEvent = {
  minute: number; extra?: number; team: number; type: string; detail?: string;
  label?: Name; player?: Person; assist?: Person;
};
export type LineupPlayer = { number?: number; pos?: string; grid?: string; player: Person };
export type Lineup = { formation?: string; coach?: { name: Name }; start: LineupPlayer[]; subs?: LineupPlayer[] };
export type MatchFull = DayMatch & {
  // venue (14 Nov 2026): {name:{ar,en}, city?:{ar,en}}; older API: plain English strings
  round?: Name; venue?: { name?: Name | string; city?: Name | string }; referee?: string;
  events?: MatchEvent[]; lineups?: { home?: Lineup; away?: Lineup };
  stats?: Record<string, Score>;
};

// Arabic labels for provider status codes
export const STATUS_AR: Record<string, string> = {
  HT: 'استراحة', FT: 'انتهت', AET: 'بعد التمديد', PEN: 'ترجيح', PST: 'مؤجلة', CANC: 'ملغاة',
  ABD: 'متوقفة', SUSP: 'معلّقة', INT: 'متوقفة', TBD: 'لم يحدد', BT: 'استراحة', P: 'ترجيح',
  NS: '', '1H': 'الشوط الأول', '2H': 'الشوط الثاني', ET: 'وقت إضافي', LIVE: 'مباشر',
};
export const LIVE_CODES = new Set(['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP']);

export function absUrl(u?: string) {
  return !u ? undefined : u.startsWith('http') ? u : SITE + u;
}
// Wrap a (possibly Latin) name in FSI/PDI isolates so it never reorders the Arabic text around it
export function iso(s: string) {
  return '\u2068' + s + '\u2069';
}

const AR = /[\u0600-\u06FF]/;
// Venue text for display: only when the API has a real Arabic name (venues_arabic.csv); English-only -> ''
export function venueAr(v?: { name?: Name | string; city?: Name | string }) {
  const n = v?.name;
  if (!n || typeof n === 'string' || !AR.test(n.ar)) return '';
  const c = v?.city;
  const city = c && typeof c !== 'string' && AR.test(c.ar) ? c.ar : '';
  return city ? `${n.ar}، ${city}` : n.ar;
}

export function teamName(t?: Team) {
  return t ? t.short?.ar || t.name.ar : '—';
}
export function kickoffLocal(iso: string) {
  return new Date(iso).toLocaleTimeString('ar', { hour: '2-digit', minute: '2-digit' });
}

export async function getJson<T>(url: string): Promise<T | null> {
  try {
    const r = await fetch(url, { cache: 'no-store' } as RequestInit);
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;
  }
}

// teams.json is ~large and identical for every screen: fetch once per app session
let teamsP: Promise<Teams> | null = null;
export function loadTeams(): Promise<Teams> {
  if (!teamsP) {
    teamsP = getJson<Teams>(API + '/teams.json').then((t) => {
      if (!t) teamsP = null;   // retry next time
      return t || {};
    });
  }
  return teamsP;
}

export async function loadLive(): Promise<Record<string, Live> | null> {
  const j = await getJson<{ m?: Record<string, Live>; f?: Record<string, Live> }>(LIVE + '/');
  return j ? { ...(j.f || {}), ...(j.m || {}) } : null;
}

// Worker /events?id= rows: [minute, extra, type g|c|s|v, detail, player, player2, side h|a, pid, pid2]
type LiveRow = [number, number, string, string, string, string, string, number | null, number | null];
const TYPE = { g: 'goal', c: 'card', s: 'subst', v: 'var' } as Record<string, string>;
const DETAIL: Record<string, string> = {
  'g:n': 'Normal Goal', 'g:p': 'Penalty', 'g:o': 'Own Goal', 'g:m': 'Missed Penalty',
  'c:y': 'Yellow Card', 'c:r': 'Red Card', 'c:yr': 'Second Yellow card',
};
export async function loadLiveEvents(id: number, home: number, away: number): Promise<MatchEvent[] | null> {
  const j = await getJson<{ l?: LiveRow[] }>(`${LIVE}/events?id=${id}`);
  if (!j || !Array.isArray(j.l)) return null;
  return j.l.map(([min, extra, t, d, p, p2, side, pid, pid2]) => ({
    minute: min, extra: extra || undefined, team: side === 'h' ? home : away,
    type: TYPE[t] || t, detail: DETAIL[`${t}:${d}`] || d,
    player: p ? { id: pid ?? undefined, name: { ar: p, en: p } } : undefined,
    assist: p2 ? { id: pid2 ?? undefined, name: { ar: p2, en: p2 } } : undefined,
  }));
}
