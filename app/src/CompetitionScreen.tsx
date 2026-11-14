// Competition screen. League: api/v1/leagues/<CODE>.json -> Table | Scorers | Matches (round matches fetched lazily,
// visible round only, max 10 requests). Cup: api/v1/cups/<CODE>.json -> Groups (if tables) | Bracket (list by stage) | Scorers.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import {
  API, MatchFull, Name, STATUS_AR, Score, Teams, absUrl, getJson, kickoffLocal, loadTeams, teamName,
} from './api';

type Zone = { code: string; label?: Name };
type TableRow = { rank?: number; pos?: number; team: number; played?: number; p?: number; w: number; d: number; l: number;
                  gf: number; ga: number; gd: number; pts: number; zone?: Zone };
type Scorer = { rank: number; player: { id?: number; name: Name; short?: Name }; team: number; goals: number };
type League = { code: string; season: number; name: Name; logo?: string; table?: TableRow[]; scorers?: Scorer[];
                rounds?: { round?: Name; matches: number[] }[] };
type Tie = { home?: number; away?: number; legs: number[]; agg?: Score; pen?: Score; winner?: number; tbd?: boolean };
type Cup = { code: string; name: Name; label?: string; logo?: string; champion?: number; scorers?: Scorer[];
             tables?: { group?: string; name?: Name; line?: number; rows: TableRow[] }[];
             rounds?: { round: Name; ties: Tie[] }[]; third_place?: Tie[] };

// same colours as the site (zones.py COLORS)
const ZONE: Record<string, string> = { cl: '#2f81f7', clq: '#39c5cf', cl2: '#f0883e', reg: '#a371f7',
  grp1: '#3fb950', grp2: '#8b949e', rpo: '#d29922', rel: '#f85149' };

const MAX_LAZY = 10;
const matchCache = new Map<number, MatchFull | null>();
async function loadMatch(id: number) {
  if (!matchCache.has(id)) matchCache.set(id, await getJson<MatchFull>(`${API}/matches/${id}.json`));
  return matchCache.get(id) ?? null;
}

type Props = NativeStackScreenProps<RootStack, 'Competition'>;

export default function CompetitionScreen({ route, navigation }: Props) {
  const { code, cup } = route.params;
  const [teams, setTeams] = useState<Teams>({});
  const [lg, setLg] = useState<League | null | undefined>(undefined);
  const [cp, setCp] = useState<Cup | null | undefined>(undefined);
  const [tab, setTab] = useState(0);

  useEffect(() => {
    loadTeams().then(setTeams);
    if (cup) getJson<Cup>(`${API}/cups/${code}.json`).then((d) => { setCp(d); if (d) navigation.setOptions({ title: d.name.ar }); });
    else getJson<League>(`${API}/leagues/${code}.json`).then((d) => { setLg(d); if (d) navigation.setOptions({ title: d.name.ar }); });
  }, [code, cup, navigation]);

  const openTeam = (id?: number) => id && navigation.push('Club', { id });
  const openMatch = (id: number) => navigation.push('Match', { id });

  const data = cup ? cp : lg;
  if (data === undefined) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (data === null) return <Text style={s.empty}>تعذّر التحميل</Text>;

  const tabs: { label: string; body: () => React.ReactNode }[] = [];
  if (lg) {
    tabs.push({ label: 'الترتيب', body: () => <Table rows={lg.table || []} teams={teams} onTeam={openTeam} /> });
    tabs.push({ label: 'الهدافون', body: () => <Scorers list={lg.scorers || []} teams={teams} onTeam={openTeam} /> });
    tabs.push({ label: 'المباريات', body: () => <Rounds lg={lg} teams={teams} onMatch={openMatch} /> });
  } else if (cp) {
    if (cp.tables?.length) tabs.push({ label: 'المجموعات', body: () => (
      <ScrollView>
        {cp.tables!.map((t, i) => (
          <View key={i}>
            {t.name?.ar || t.group ? <Text style={s.groupHead}>{t.name?.ar || t.group}</Text> : null}
            <Table rows={t.rows} teams={teams} onTeam={openTeam} line={t.line} scroll={false} />
          </View>
        ))}
      </ScrollView>
    ) });
    tabs.push({ label: 'الأدوار', body: () => <Bracket cup={cp} teams={teams} onTeam={openTeam} onMatch={openMatch} /> });
    tabs.push({ label: 'الهدافون', body: () => <Scorers list={cp.scorers || []} teams={teams} onTeam={openTeam} /> });
  }
  const cur = Math.min(tab, tabs.length - 1);

  return (
    <View style={s.root}>
      <View style={s.tabs}>
        {tabs.map((t, i) => (
          <Pressable key={t.label} onPress={() => setTab(i)} style={[s.tab, i === cur && s.tabOn]}>
            <Text style={[s.tabTx, i === cur && s.tabTxOn]}>{t.label}</Text>
          </Pressable>
        ))}
      </View>
      <View style={{ flex: 1 }}>{tabs[cur].body()}</View>
    </View>
  );
}

function TeamCell({ id, teams }: { id?: number; teams: Teams }) {
  const t = id != null ? teams[String(id)] : undefined;
  const logo = absUrl(t?.logo);
  return (
    <View style={s.teamCell}>
      {logo ? <Image source={{ uri: logo }} style={s.logo} /> : <View style={s.logo} />}
      <Text style={s.teamName} numberOfLines={1}>{id != null ? teamName(t) : 'لم يتحدد'}</Text>
    </View>
  );
}

function Table({ rows, teams, onTeam, line, scroll = true }: {
  rows: TableRow[]; teams: Teams; onTeam: (id: number) => void; line?: number; scroll?: boolean;
}) {
  const head = (
    <View style={[s.tr, s.th]}>
      <Text style={s.cPos}>#</Text><Text style={[s.cTeam, s.thTx]}>الفريق</Text>
      {['لعب', 'ف', 'ت', 'خ', '+/-', 'نقاط'].map((h) => <Text key={h} style={[s.cNum, s.thTx]}>{h}</Text>)}
    </View>
  );
  const zones = new Map<string, Zone>();
  const body = rows.map((r) => {
    const pos = r.rank ?? r.pos ?? 0;
    if (r.zone) zones.set(r.zone.code, r.zone);
    return (
      <Pressable key={r.team} onPress={() => onTeam(r.team)}
                 style={[s.tr, line != null && pos === line && s.cutLine]}>
        <View style={[s.zoneBar, r.zone && { backgroundColor: ZONE[r.zone.code] || 'transparent' }]} />
        <Text style={s.cPos}>{pos}</Text>
        <View style={s.cTeam}><TeamCell id={r.team} teams={teams} /></View>
        {[r.played ?? r.p, r.w, r.d, r.l, r.gd > 0 ? `+${r.gd}` : r.gd, r.pts].map((v, i) => (
          <Text key={i} style={[s.cNum, i === 5 && s.pts]}>{v}</Text>
        ))}
      </Pressable>
    );
  });
  const legend = zones.size ? (
    <View style={s.legend}>
      {[...zones.values()].map((z) => (
        <View key={z.code} style={s.legendItem}>
          <View style={[s.legendDot, { backgroundColor: ZONE[z.code] || '#999' }]} />
          <Text style={s.legendTx}>{z.label?.ar || z.code}</Text>
        </View>
      ))}
    </View>
  ) : null;
  const inner = <>{head}{body}{legend}</>;
  return scroll ? <ScrollView>{inner}</ScrollView> : <View>{inner}</View>;
}

function Scorers({ list, teams, onTeam }: { list: Scorer[]; teams: Teams; onTeam: (id: number) => void }) {
  if (!list.length) return <Text style={s.empty}>لا هدافين بعد</Text>;
  return (
    <FlatList
      data={list}
      keyExtractor={(x, i) => `${x.player.id ?? x.player.name.en}-${i}`}
      renderItem={({ item }) => (
        <Pressable style={s.tr} onPress={() => onTeam(item.team)}>
          <Text style={s.cPos}>{item.rank}</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.scName} numberOfLines={1}>{item.player.short?.ar || item.player.name.ar}</Text>
            <Text style={s.scTeam} numberOfLines={1}>{teamName(teams[String(item.team)])}</Text>
          </View>
          <Text style={[s.cNum, s.pts]}>{item.goals}</Text>
        </Pressable>
      )}
    />
  );
}

function Rounds({ lg, teams, onMatch }: { lg: League; teams: Teams; onMatch: (id: number) => void }) {
  const rounds = lg.rounds || [];
  // default = next round to play: max games played in the table (rounds in order) -> that index
  const start = useMemo(() => {
    const played = Math.max(0, ...(lg.table || []).map((r) => r.played ?? 0));
    return Math.min(played, Math.max(0, rounds.length - 1));
  }, [lg, rounds.length]);
  const [ri, setRi] = useState(start);
  const [ms, setMs] = useState<(MatchFull | null)[] | null>(null);
  const ids = rounds[ri]?.matches || [];

  useEffect(() => {
    let live = true;
    setMs(null);
    Promise.all(ids.slice(0, MAX_LAZY).map(loadMatch)).then((r) => live && setMs(r));
    return () => { live = false; };
  }, [ri]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rounds.length) return <Text style={s.empty}>لا مباريات</Text>;
  return (
    <View style={{ flex: 1 }}>
      <View style={s.roundBar}>
        <Pressable disabled={ri <= 0} onPress={() => setRi(ri - 1)} style={s.roundBtn}>
          <Text style={[s.roundArrow, ri <= 0 && s.dim]}>›</Text>
        </Pressable>
        <Text style={s.roundTx}>{rounds[ri].round?.ar || `الجولة ${ri + 1}`}</Text>
        <Pressable disabled={ri >= rounds.length - 1} onPress={() => setRi(ri + 1)} style={s.roundBtn}>
          <Text style={[s.roundArrow, ri >= rounds.length - 1 && s.dim]}>‹</Text>
        </Pressable>
      </View>
      {ms === null ? <ActivityIndicator style={{ marginTop: 30 }} /> : (
        <ScrollView>
          {ids.map((id, i) => {
            const m = i < MAX_LAZY ? ms[i] : undefined;
            return (
              <Pressable key={id} onPress={() => onMatch(id)} style={s.mRow}>
                {m ? <MatchLine m={m} teams={teams} /> : <Text style={s.empty}>مباراة {id}</Text>}
              </Pressable>
            );
          })}
          {ids.length > MAX_LAZY ? <Text style={s.note}>عُرضت أول {MAX_LAZY} مباريات بالتفصيل</Text> : null}
        </ScrollView>
      )}
    </View>
  );
}

function MatchLine({ m, teams }: { m: MatchFull; teams: Teams }) {
  const done = m.score && !['NS', 'TBD', 'PST'].includes(m.status);
  return (
    <View style={s.mLine}>
      <View style={{ flex: 1 }}><TeamCell id={m.home} teams={teams} /></View>
      <View style={s.mMid}>
        <Text style={s.mScore}>{done ? `${m.score!.h} - ${m.score!.a}` : kickoffLocal(m.kickoff)}</Text>
        <Text style={s.mSub}>{done ? STATUS_AR[m.status] || '' : new Date(m.kickoff).toLocaleDateString('ar', { day: 'numeric', month: 'short' })}</Text>
      </View>
      <View style={{ flex: 1 }}><TeamCell id={m.away} teams={teams} /></View>
    </View>
  );
}

function Bracket({ cup, teams, onTeam, onMatch }: {
  cup: Cup; teams: Teams; onTeam: (id?: number) => void; onMatch: (id: number) => void;
}) {
  const stages = [...(cup.rounds || [])];
  if (cup.third_place?.length) stages.push({ round: { ar: 'المركز الثالث', en: 'Third place' }, ties: cup.third_place });
  if (!stages.length) return <Text style={s.empty}>لا أدوار إقصائية بعد</Text>;
  return (
    <ScrollView>
      {cup.champion ? (
        <Pressable onPress={() => onTeam(cup.champion)} style={s.champ}>
          <Text style={s.champTx}>🏆 البطل</Text>
          <TeamCell id={cup.champion} teams={teams} />
        </Pressable>
      ) : null}
      {stages.map((st, i) => (
        <View key={i}>
          <Text style={s.groupHead}>{st.round.ar}</Text>
          {st.ties.map((t, j) => <TieRow key={j} t={t} teams={teams} onMatch={onMatch} />)}
        </View>
      ))}
    </ScrollView>
  );
}

function TieRow({ t, teams, onMatch }: { t: Tie; teams: Teams; onMatch: (id: number) => void }) {
  const leg = t.legs[t.legs.length - 1];
  const side = (id?: number) => (
    <View style={[{ flex: 1 }, t.winner != null && id === t.winner && s.winner]}><TeamCell id={id} teams={teams} /></View>
  );
  return (
    <Pressable disabled={!leg} onPress={() => leg && onMatch(leg)} style={s.mRow}>
      <View style={s.mLine}>
        {side(t.home)}
        <View style={s.mMid}>
          <Text style={s.mScore}>{t.tbd || !t.agg ? '—' : `${t.agg.h} - ${t.agg.a}`}</Text>
          {t.pen ? <Text style={s.mSub}>ترجيح {t.pen.h} - {t.pen.a}</Text> : t.legs.length > 1 ? <Text style={s.mSub}>مجموع المباراتين</Text> : null}
        </View>
        {side(t.away)}
      </View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  empty: { textAlign: 'center', marginTop: 30, color: '#777' },
  note: { textAlign: 'center', color: '#777', fontSize: 12, padding: 8 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderColor: '#ddd' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabOn: { borderBottomWidth: 2, borderColor: '#17803a' },
  tabTx: { fontSize: 15, color: '#555' },
  tabTxOn: { color: '#17803a', fontWeight: '700' },
  tr: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, paddingHorizontal: 8,
        borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5' },
  th: { backgroundColor: '#f2f3f5' },
  thTx: { fontWeight: '700', color: '#555', fontSize: 12 },
  zoneBar: { position: 'absolute', right: 0, top: 0, bottom: 0, width: 3 },
  cutLine: { borderBottomWidth: 2, borderBottomColor: '#17803a' },
  cPos: { width: 24, textAlign: 'center', color: '#555' },
  cTeam: { flex: 1 },
  cNum: { width: 32, textAlign: 'center', fontSize: 13 },
  pts: { fontWeight: '800' },
  teamCell: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  logo: { width: 22, height: 22, resizeMode: 'contain' },
  teamName: { flexShrink: 1, fontSize: 14, textAlign: 'right' },
  legend: { padding: 10, gap: 6 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendTx: { fontSize: 12, color: '#555' },
  groupHead: { fontWeight: '700', backgroundColor: '#f2f3f5', padding: 8, marginTop: 8, textAlign: 'right' },
  scName: { fontSize: 14, fontWeight: '600', textAlign: 'right' },
  scTeam: { fontSize: 12, color: '#777', textAlign: 'right' },
  roundBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 8,
              borderBottomWidth: 1, borderColor: '#eee' },
  roundBtn: { padding: 10 },
  roundArrow: { fontSize: 26, color: '#17803a' },
  dim: { color: '#ccc' },
  roundTx: { fontWeight: '700', fontSize: 15 },
  mRow: { borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5', paddingVertical: 10, paddingHorizontal: 8 },
  mLine: { flexDirection: 'row', alignItems: 'center' },
  mMid: { width: 80, alignItems: 'center' },
  mScore: { fontWeight: '700', fontSize: 15 },
  mSub: { fontSize: 11, color: '#666' },
  winner: { backgroundColor: '#e8f5ec', borderRadius: 6 },
  champ: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: '#fff8e1' },
  champTx: { fontWeight: '700' },
});
