// Search (M5): same data and matching as saffara.app/search.html.
//   assets/search_top.js  window.FBSEARCH = {c: all clubs [id, ar, en, league, …], p: top 150 players, n: player count}
//   assets/search_full.js window.FBSEARCH_P = all players [ar, en, club_id, slug-field, player_id|0] (loaded on first query)
//   Leagues/cups: api/v1/index.json (the site's search has the 10 leagues only, no cups).
// norm()/tier() are ports of search.html (lower case, accents, أإآٱ->ا, ة->ه, ى->ي, tashkeel, "ال" at word start).
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Pressable, SectionList, StyleSheet, Text, TextInput, View } from 'react-native';
import type { RootStack } from '../App';
import { API, Comp, SITE, Teams, absUrl, getJson, iso, loadTeams, teamName } from './api';
import { hasPlayerId } from './nav';
import { countryKeys } from './countries';

type ClubRow = [number, string, string, string, ...unknown[]];
type PlayerRow = [string, string, number, unknown, number];
type Hit =
  | { k: 'l'; code: string; cup: boolean; ar: string; en: string; logo?: string }
  | { k: 'c'; id: number; ar: string; en: string }
  | { k: 'p'; id: number; ar: string; en: string; club: number };

const MAX_PER_GROUP = 25;

export function norm(s?: string) {
  if (!s) return '';
  s = ('' + s).toLowerCase();
  s = s.normalize('NFD').replace(/[̀-ͯٓ-ٕ]/g, '');
  s = s.replace(/[أإآٱ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي').replace(/[ً-ْـ]/g, '');
  s = s.replace(/(^|\s)ال(?=\S{2,})/g, '$1');
  return s.replace(/[-'.’]/g, ' ').replace(/\s+/g, ' ').trim();
}
// 0 exact · 1 first word starts with q · 2 later word starts with q · 3 inside a word (2-letter queries only) · 9 none
function tier(name: string, q: string) {
  if (!name || !q) return 9;
  if (name === q) return 0;
  if (q.includes(' ')) {
    if (name.startsWith(q)) return 1;
    if (name.includes(' ' + q)) return 2;
  } else {
    const w = name.split(' ');
    if (w[0].startsWith(q)) return 1;
    for (let k = 1; k < w.length; k++) if (w[k].startsWith(q)) return 2;
  }
  if (name.includes(q) && q.length === 2) return 3;
  return 9;
}
const best = (q: string, ...names: string[]) => Math.min(...names.map((n) => tier(n, q)));

// the index files are JS (window.X=...;) -> strip the assignment and parse the JSON
async function loadJsVar<T>(path: string, v: string): Promise<T | null> {
  try {
    const r = await fetch(SITE + path);
    if (!r.ok) return null;
    const t = await r.text();
    return JSON.parse(t.replace(new RegExp('^[\\s\\S]*?window\\.' + v + '='), '').trim().replace(/;$/, '')) as T;
  } catch {
    return null;
  }
}
let topP: Promise<{ c: ClubRow[]; p: PlayerRow[]; n: number } | null> | null = null;
let fullP: Promise<PlayerRow[] | null> | null = null;

type Prepared<T> = { row: T; keys: string[] };

export default function SearchScreen({ navigation }: NativeStackScreenProps<RootStack, 'Search'>) {
  const [q, setQ] = useState('');
  const [teams, setTeams] = useState<Teams>({});
  const [comps, setComps] = useState<Prepared<Comp & { cup: boolean }>[]>([]);
  const [clubs, setClubs] = useState<Prepared<ClubRow>[] | null>(null);
  const [players, setPlayers] = useState<Prepared<PlayerRow>[]>([]);
  const [fullState, setFullState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');

  useEffect(() => {
    loadTeams().then(setTeams);
    getJson<{ leagues?: Comp[]; cups?: Comp[] }>(API + '/index.json').then((i) => {
      const all = [...(i?.leagues || []).map((c) => ({ ...c, cup: false })), ...(i?.cups || []).map((c) => ({ ...c, cup: true }))];
      // names + code + the country's names/aliases/code (السعودية / Saudi / KSA -> Saudi league and Saudi cups)
      setComps(all.map((c) => ({ row: c, keys: [norm(c.name.ar), norm(c.name.en), norm(c.code), ...countryKeys(c.code).map(norm)] })));
    });
    if (!topP) topP = loadJsVar('/assets/search_top.js', 'FBSEARCH');
    topP.then((d) => {
      if (!d) { topP = null; setClubs([]); return; }
      setClubs(d.c.map((c) => ({ row: c, keys: [norm(c[1]), norm(c[2])] })));
      setPlayers(d.p.map((p) => ({ row: p, keys: [norm(p[0]), norm(p[1])] })));
    });
  }, []);

  // all players: load once, on the first query (like the site)
  useEffect(() => {
    if (!q.trim() || fullState !== 'idle') return;
    setFullState('loading');
    if (!fullP) fullP = loadJsVar<PlayerRow[]>('/assets/search_full.js', 'FBSEARCH_P');
    fullP.then((d) => {
      if (!d) { fullP = null; setFullState('error'); return; }
      setPlayers(d.map((p) => ({ row: p, keys: [norm(p[0]), norm(p[1])] })));
      setFullState('done');
    });
  }, [q, fullState]);

  const sections = useMemo(() => {
    const nq = norm(q);
    if (!nq) return [];
    const rank = <T,>(list: Prepared<T>[]) => list
      .map((x, i) => ({ x, t: best(nq, ...x.keys), i }))
      .filter((r) => r.t < 9)
      .sort((a, b) => a.t - b.t || a.i - b.i)
      .slice(0, MAX_PER_GROUP)
      .map((r) => r.x.row);
    const out: { title: string; data: Hit[] }[] = [];
    const L = rank(comps).map((c): Hit => ({ k: 'l', code: c.code, cup: c.cup, ar: c.name.ar, en: c.name.en, logo: c.logo }));
    const C = rank(clubs || []).map((c): Hit => ({ k: 'c', id: c[0], ar: c[1], en: c[2] }));
    const P = rank(players).map((p): Hit => ({ k: 'p', id: p[4], ar: p[0], en: p[1], club: p[2] }));
    if (L.length) out.push({ title: 'البطولات', data: L });
    if (C.length) out.push({ title: 'الأندية', data: C });
    if (P.length) out.push({ title: 'اللاعبون', data: P });
    return out;
  }, [q, comps, clubs, players]);

  const open = (h: Hit) => {
    if (h.k === 'l') navigation.push('Competition', { code: h.code, cup: h.cup });
    else if (h.k === 'c') navigation.push('Club', { id: h.id });
    else if (hasPlayerId(h.id)) navigation.push('Player', { id: h.id, name: h.ar || h.en });
    else navigation.push('Club', { id: h.club });   // no player id (like the site: the club page)
  };

  return (
    <View style={s.root}>
      <View style={s.boxWrap}>
        <TextInput
          value={q}
          onChangeText={setQ}
          placeholder="ابحث عن نادٍ أو لاعب أو بطولة"
          placeholderTextColor="#999"
          style={s.box}
          autoFocus
          autoCorrect={false}
          autoCapitalize="none"
          returnKeyType="search"
          clearButtonMode="while-editing"
        />
      </View>
      {clubs === null ? <ActivityIndicator style={{ marginTop: 30 }} /> : (
        <SectionList
          sections={sections}
          keyboardShouldPersistTaps="handled"
          keyExtractor={(h, i) => `${h.k}-${h.k === 'l' ? h.code : h.id}-${i}`}
          renderSectionHeader={({ section }) => <Text style={s.secHead}>{section.title}</Text>}
          renderItem={({ item }) => <HitRow h={item} teams={teams} onPress={() => open(item)} />}
          ListEmptyComponent={q.trim() ? <Text style={s.empty}>لا نتائج</Text> : (
            <Text style={s.empty}>{clubs.length} نادياً و{players.length} لاعباً جاهزة للبحث</Text>
          )}
          ListFooterComponent={q.trim() && fullState === 'loading'
            ? <Text style={s.note}>تحميل كل اللاعبين…</Text> : undefined}
          stickySectionHeadersEnabled
        />
      )}
    </View>
  );
}

function HitRow({ h, teams, onPress }: { h: Hit; teams: Teams; onPress: () => void }) {
  let logo: string | undefined;
  let sub = '';
  if (h.k === 'l') { logo = absUrl(h.logo); sub = h.cup ? 'كأس' : 'دوري'; }
  else if (h.k === 'c') logo = absUrl(teams[String(h.id)]?.logo);
  else { logo = absUrl(teams[String(h.club)]?.logo); sub = teamName(teams[String(h.club)]); }
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.row, pressed && s.pressed]}>
      {logo ? <Image source={{ uri: logo }} style={s.logo} /> : <View style={s.logo} />}
      <View style={{ flex: 1 }}>
        <Text style={s.name} numberOfLines={1}>{iso(h.ar || h.en)}</Text>
        {sub ? <Text style={s.sub} numberOfLines={1}>{iso(sub)}</Text> : null}
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  boxWrap: { padding: 10, borderBottomWidth: 1, borderColor: '#eee' },
  box: { backgroundColor: '#f2f3f5', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16,
         textAlign: 'right', writingDirection: 'rtl' },
  secHead: { fontWeight: '700', backgroundColor: '#f2f3f5', padding: 8, textAlign: 'right' },
  empty: { textAlign: 'center', marginTop: 30, color: '#777' },
  note: { textAlign: 'center', color: '#777', fontSize: 12, padding: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 12,
         borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5' },
  pressed: { backgroundColor: '#f5f5f5' },
  logo: { width: 28, height: 28, resizeMode: 'contain' },
  name: { fontSize: 15, textAlign: 'right', writingDirection: 'rtl' },
  sub: { fontSize: 12, color: '#777', textAlign: 'right', writingDirection: 'rtl' },
});
