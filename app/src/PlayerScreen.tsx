// Player screen (M4): api/v1/players/<id>.json. Photo (api-sports CDN, hidden on error), Arabic name, club, position/number,
// season stats (league only: make_api.py excludes cups), recent matches (ids, fetched lazily, max 10).
// Only current-season league players have a file (404 otherwise) -> fall back to the name passed by the caller.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import { API, Comp, MatchFull, Name, Teams, absUrl, getJson, iso, loadTeams, teamName } from './api';
import { MatchLine, loadMatch } from './CompetitionScreen';

type Stat = { league: string; season: number; apps?: number; starts?: number; minutes?: number; goals?: number;
              assists?: number; rating?: number; yellow?: number; red?: number };
type Player = {
  id: number; name: Name; short?: Name; full_name?: { ar?: string; en?: string }; team?: number; number?: number;
  pos?: string; pos_code?: string; nationality?: string; height?: string; age?: number; birth?: string;
  stats?: Stat[]; matches?: number[];
  photo?: boolean;   // false = provider's generic grey picture (player_info.has_photo = 0): show the placeholder
};

const POS_AR: Record<string, string> = { G: 'حارس مرمى', D: 'مدافع', M: 'لاعب وسط', F: 'مهاجم' };
const MAX_MATCHES = 10;
const photoUrl = (id: number) => `https://media.api-sports.io/football/players/${id}.png`;

// Same as the site (player_layout.season_label): league season 2026 -> "2026/27"; cups use index.json cups[].label
// for their current season (some cups are single-year, e.g. "2026").
function seasonLabel(code: string, season: number, comps: Comp[]) {
  const c = comps.find((x) => x.code === code) as (Comp & { label?: string; season?: number }) | undefined;
  if (c?.type && c.label && c.season === season) return c.label;
  return `${season}/${String(season + 1).slice(-2)}`;
}

let compsP: Promise<Comp[]> | null = null;
function loadComps(): Promise<Comp[]> {
  if (!compsP) compsP = getJson<{ leagues?: Comp[]; cups?: Comp[] }>(API + '/index.json')
    .then((i) => [...(i?.leagues || []), ...(i?.cups || []).map((c) => ({ ...c, type: c.type || 'cup' }))]);
  return compsP;
}

export default function PlayerScreen({ route, navigation }: NativeStackScreenProps<RootStack, 'Player'>) {
  const { id, name: fallbackName } = route.params;
  const [p, setP] = useState<Player | null | undefined>(undefined);
  const [teams, setTeams] = useState<Teams>({});
  const [comps, setComps] = useState<Comp[]>([]);
  const [photoOk, setPhotoOk] = useState(true);
  const [ms, setMs] = useState<(MatchFull | null)[] | null>(null);
  const [squadNo, setSquadNo] = useState<number | undefined>();

  useEffect(() => {
    loadTeams().then(setTeams);
    loadComps().then(setComps);
    getJson<Player>(`${API}/players/${id}.json`).then((d) => {
      setP(d);
      const n = d?.name.ar || fallbackName;
      if (n) navigation.setOptions({ title: n });
    });
  }, [id, fallbackName, navigation]);

  // Shirt number: the club squad (provider squads endpoint, = league lineups) wins over player_info.number, which can be
  // another team's number (e.g. 579603: player_info 1 = GCC Champions League, squad/lineups 81)
  useEffect(() => {
    if (p?.team == null) return;
    getJson<{ squad?: { player?: { id?: number }; number?: number }[] }>(`${API}/teams/${p.team}.json`).then((c) => {
      const n = c?.squad?.find((x) => x.player?.id === id)?.number;
      if (n != null) setSquadNo(n);
    });
  }, [p?.team, id]);

  useEffect(() => {
    if (__DEV__) console.log('[player photo]', photoUrl(id));
  }, [id]);

  useEffect(() => {
    if (!p?.matches?.length) { setMs([]); return; }
    let live = true;
    Promise.all(p.matches.slice(0, MAX_MATCHES).map(loadMatch)).then((r) => live && setMs(r));
    return () => { live = false; };
  }, [p]);

  const club = p?.team != null ? teams[String(p.team)] : undefined;
  const clubLogo = absUrl(club?.logo);
  const lgName = (code: string) => comps.find((c) => c.code === code)?.name.ar || code;
  // cups are tagged in comps by loadComps (index.json cups[])
  const isCupCode = (code: string) => !!comps.find((c) => c.code === code)?.type;
  const fullEn = p?.full_name?.ar || (p?.full_name?.en && p.full_name.en !== p.name.en ? p.full_name.en : '');

  return (
    <ScrollView style={s.root}>
      <View style={s.head}>
        {photoOk && p?.photo !== false ? (
          <Image source={{ uri: photoUrl(id) }} style={s.photo} onError={() => setPhotoOk(false)} />
        ) : <View style={[s.photo, s.noPhoto]}><Text style={s.noPhotoTx}>👤</Text></View>}
        <View style={{ flex: 1 }}>
          <Text style={s.name}>{iso(p?.name.ar || fallbackName || '—')}</Text>
          {fullEn ? <Text style={s.meta}>{iso(fullEn)}</Text> : null}
          {p?.team != null ? (
            <Pressable onPress={() => navigation.push('Club', { id: p.team! })} style={s.clubRow}>
              {clubLogo ? <Image source={{ uri: clubLogo }} style={s.clubLogo} /> : null}
              <Text style={s.clubTx}>{iso(teamName(club))}</Text>
            </Pressable>
          ) : null}
          {p ? (
            <Text style={s.meta}>
              {[p.pos_code ? POS_AR[p.pos_code] : p.pos, (squadNo ?? p.number) != null ? `الرقم ${squadNo ?? p.number}` : '',
                p.age ? `${p.age} سنة` : ''].filter(Boolean).join(' · ')}
            </Text>
          ) : null}
        </View>
      </View>

      {p === undefined ? <ActivityIndicator style={{ marginTop: 30 }} /> : p === null ? (
        <Text style={s.empty}>لا بيانات تفصيلية لهذا اللاعب (ليس بدوري الموسم الحالي)</Text>
      ) : (
        <>
          {p.stats?.length ? (() => {
            // current = the competition's current season in index.json (leagues[]/cups[].season); unknown code -> newest season
            const newest = Math.max(...p.stats!.map((x) => x.season));
            const isCur = (st: Stat) => {
              const c = comps.find((x) => x.code === st.league);
              return c?.season != null ? c.season === st.season : st.season === newest;
            };
            const cur = p.stats!.filter(isCur);
            const old = p.stats!.filter((st) => !isCur(st)).sort((a, b) => b.season - a.season);
            const block = (st: Stat, i: number) => (
              <View key={`${st.league}-${st.season}-${i}`} style={s.statBlock}>
                <View style={s.statHead}>
                  <Text style={s.statLg}>{iso(lgName(st.league))} · {seasonLabel(st.league, st.season, comps)}</Text>
                  {isCupCode(st.league) ? <Text style={s.cupTag}>كأس</Text> : null}
                </View>
                <View style={s.grid}>
                  <Cell label="مباريات" v={st.apps} />
                  <Cell label="أساسي" v={st.starts} />
                  <Cell label="أهداف" v={st.goals} />
                  <Cell label="صناعة" v={st.assists} />
                  <Cell label="صفراء" v={st.yellow} />
                  <Cell label="حمراء" v={st.red} />
                  {st.minutes != null ? <Cell label="دقائق" v={st.minutes} /> : null}
                  {st.rating != null ? <Cell label="التقييم" v={st.rating} /> : null}
                </View>
              </View>
            );
            return (
              <View>
                {cur.length ? <Text style={s.secHead}>الموسم الحالي</Text> : null}
                {cur.map(block)}
                {old.length ? <Text style={s.secHead}>مواسم سابقة</Text> : null}
                {old.map(block)}
              </View>
            );
          })() : null}

          {p.matches?.length ? (
            <View>
              <Text style={s.secHead}>آخر المباريات</Text>
              {ms === null ? <ActivityIndicator style={{ margin: 20 }} /> : p.matches.slice(0, MAX_MATCHES).map((mid, i) => (
                <Pressable key={mid} onPress={() => navigation.push('Match', { id: mid })} style={s.mRow}>
                  {ms[i] ? <MatchLine m={ms[i]!} teams={teams} /> : <Text style={s.empty}>مباراة {mid}</Text>}
                </Pressable>
              ))}
            </View>
          ) : null}
        </>
      )}
      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

function Cell({ label, v }: { label: string; v?: number }) {
  return (
    <View style={s.cell}>
      <Text style={s.cellV}>{v ?? 0}</Text>
      <Text style={s.cellL}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  empty: { textAlign: 'center', marginTop: 20, color: '#777', paddingHorizontal: 16 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderBottomWidth: 1, borderColor: '#eee' },
  photo: { width: 84, height: 84, borderRadius: 42, backgroundColor: '#f2f3f5' },
  noPhoto: { alignItems: 'center', justifyContent: 'center' },
  noPhotoTx: { fontSize: 36, color: '#bbb' },
  name: { fontSize: 20, fontWeight: '700', writingDirection: 'rtl', textAlign: 'right' },
  meta: { fontSize: 13, color: '#666', marginTop: 3, writingDirection: 'rtl', textAlign: 'right' },
  clubRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 },
  clubLogo: { width: 20, height: 20, resizeMode: 'contain' },
  clubTx: { fontSize: 14, color: '#17803a', fontWeight: '600' },
  secHead: { fontWeight: '700', backgroundColor: '#f2f3f5', padding: 8, marginTop: 12, textAlign: 'right' },
  statBlock: { paddingHorizontal: 10, paddingTop: 8 },
  statHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  cupTag: { fontSize: 11, color: '#fff', backgroundColor: '#f0883e', borderRadius: 4, paddingHorizontal: 6, overflow: 'hidden' },
  statLg: { fontWeight: '600', color: '#444', textAlign: 'right', marginBottom: 6 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  cell: { width: '30%', backgroundColor: '#f7f8f9', borderRadius: 8, paddingVertical: 8, alignItems: 'center' },
  cellV: { fontSize: 18, fontWeight: '800' },
  cellL: { fontSize: 12, color: '#666' },
  mRow: { borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5', paddingVertical: 10, paddingHorizontal: 8 },
});
