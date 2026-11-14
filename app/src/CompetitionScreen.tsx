// Competition screen. League: api/v1/leagues/<CODE>.json -> Table | Scorers | Matches (round matches fetched lazily,
// visible round only, max 10 requests). Cup: api/v1/cups/<CODE>.json -> Groups (if tables) | Bracket (list by stage) | Scorers.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useMemo, useState } from 'react';
import { hasPlayerId, useOpenPlayer } from './nav';
import { ActivityIndicator, FlatList, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import {
  API, MatchFull, Name, STATUS_AR, Score, Teams, absUrl, getJson, iso, kickoffLocal, loadTeams, teamName,
} from './api';

type Zone = { code: string; label?: Name };
export type TableRow = { rank?: number; pos?: number; team: number; played?: number; p?: number; w: number; d: number; l: number;
                  gf: number; ga: number; gd: number; pts: number; zone?: Zone };
type Scorer = { rank: number; player: { id?: number; name: Name; short?: Name }; team: number; goals: number };
export type League = { code: string; season: number; name: Name; logo?: string; table?: TableRow[]; scorers?: Scorer[];
                rounds?: { round?: Name; matches: number[]; rows?: Row[] }[]; current_round?: number };
type Tie = { home?: number; away?: number; legs: number[]; rows?: Row[]; agg?: Score; pen?: Score; winner?: number; tbd?: boolean };
type Cup = { code: string; name: Name; label?: string; logo?: string; champion?: number; scorers?: Scorer[];
             tables?: { group?: string; name?: Name; line?: number; rows: TableRow[] }[];
             rounds?: { round: Name; ties: Tie[] }[]; third_place?: Tie[];
             group_rounds?: RoundData[]; current_round?: number };

// same colours as the site (zones.py COLORS)
const ZONE: Record<string, string> = { cl: '#2f81f7', clq: '#39c5cf', cl2: '#f0883e', reg: '#a371f7',
  grp1: '#3fb950', grp2: '#8b949e', rpo: '#d29922', rel: '#f85149' };

const MAX_LAZY = 10;
const matchCache = new Map<number, MatchFull | null>();
export async function loadMatch(id: number) {
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
    // opens at current_round (API); older API: next round by games played in the table
    const played = Math.max(0, ...(lg.table || []).map((r) => r.played ?? 0));
    tabs.push({ label: 'المباريات', body: () => (
      <Rounds rounds={lg.rounds || []} current={lg.current_round} fallbackStart={played} teams={teams} onMatch={openMatch} />
    ) });
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
    if (cp.group_rounds?.length) tabs.push({ label: 'المباريات', body: () => (
      <Rounds rounds={cp.group_rounds!} current={cp.current_round} teams={teams} onMatch={openMatch} />
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

export function TeamCell({ id, teams }: { id?: number; teams: Teams }) {
  const t = id != null ? teams[String(id)] : undefined;
  const logo = absUrl(t?.logo);
  return (
    <View style={s.teamCell}>
      {logo ? <Image source={{ uri: logo }} style={s.logo} /> : <View style={s.logo} />}
      <Text style={s.teamName} numberOfLines={1}>{id != null ? teamName(t) : 'لم يتحدد'}</Text>
    </View>
  );
}

export function Table({ rows, teams, onTeam, line, scroll = true, highlight }: {
  rows: TableRow[]; teams: Teams; onTeam: (id: number) => void; line?: number; scroll?: boolean; highlight?: number;
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
                 style={[s.tr, line != null && pos === line && s.cutLine, r.team === highlight && s.hl]}>
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
  const openPlayer = useOpenPlayer();
  if (!list.length) return <Text style={s.empty}>لا هدافين بعد</Text>;
  return (
    <FlatList
      data={list}
      keyExtractor={(x, i) => `${x.player.id ?? x.player.name.en}-${i}`}
      renderItem={({ item }) => (
        <Pressable style={s.tr} onPress={() => hasPlayerId(item.player.id) ? openPlayer(item.player.id, item.player.name.ar) : onTeam(item.team)}>
          <Text style={s.cPos}>{item.rank}</Text>
          <View style={{ flex: 1 }}>
            <Text style={[s.scName, hasPlayerId(item.player.id) && s.link]} numberOfLines={1}>{iso(item.player.short?.ar || item.player.name.ar)}</Text>
            <Text style={s.scTeam} numberOfLines={1}>{teamName(teams[String(item.team)])}</Text>
          </View>
          <Text style={[s.cNum, s.pts]}>{item.goals}</Text>
        </Pressable>
      )}
    />
  );
}

// api/v1 match_row (14 Nov 2026): {id, ko|date, st, h, a, s?[h,a], p?[h,a]} inside rounds/ties/group_rounds
export type Row = { id: number; ko?: string; date?: string; st: string; h: number; a: number; s?: [number, number]; p?: [number, number] };
// current: the API marks the round holding the next match (15 Nov 2026); current_round is its index in rounds[]
type RoundData = { round?: Name; matches?: number[]; rows?: Row[]; current?: boolean };

// Rounds pager: uses rows when the API has them (no per-match fetch); older API without rows -> lazy fetch (max 10)
function Rounds({ rounds, current, fallbackStart, teams, onMatch }: {
  rounds: RoundData[]; current?: number; fallbackStart?: number; teams: Teams; onMatch: (id: number) => void;
}) {
  const flagged = rounds.findIndex((r) => r.current);
  const start = Math.min(Math.max(0, flagged >= 0 ? flagged : current ?? fallbackStart ?? 0), Math.max(0, rounds.length - 1));
  const [ri, setRi] = useState(start);
  const [ms, setMs] = useState<(MatchFull | null)[] | null>(null);
  const rd = rounds[ri];
  const ids = rd?.rows ? rd.rows.map((r) => r.id) : rd?.matches || [];

  useEffect(() => {
    if (rd?.rows) { setMs([]); return; }
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
        <Text style={s.roundTx}>{rd.round?.ar || `الجولة ${ri + 1}`}</Text>
        <Pressable disabled={ri >= rounds.length - 1} onPress={() => setRi(ri + 1)} style={s.roundBtn}>
          <Text style={[s.roundArrow, ri >= rounds.length - 1 && s.dim]}>‹</Text>
        </Pressable>
      </View>
      {ms === null ? <ActivityIndicator style={{ marginTop: 30 }} /> : (
        <ScrollView>
          {rd.rows ? rd.rows.map((r) => (
            <Pressable key={r.id} onPress={() => onMatch(r.id)} style={s.mRow}>
              <RowLine r={r} teams={teams} />
            </Pressable>
          )) : ids.map((id, i) => {
            const m = i < MAX_LAZY ? ms[i] : undefined;
            return (
              <Pressable key={id} onPress={() => onMatch(id)} style={s.mRow}>
                {m ? <MatchLine m={m} teams={teams} /> : <Text style={s.empty}>مباراة {id}</Text>}
              </Pressable>
            );
          })}
          {!rd.rows && ids.length > MAX_LAZY ? <Text style={s.note}>عُرضت أول {MAX_LAZY} مباريات بالتفصيل</Text> : null}
        </ScrollView>
      )}
    </View>
  );
}

export function RowLine({ r, teams }: { r: Row; teams: Teams }) {
  const done = r.s && !['NS', 'TBD', 'PST'].includes(r.st);
  const when = r.ko ? new Date(r.ko) : r.date ? new Date(r.date + 'T00:00:00') : null;
  return (
    <View style={s.mLine}>
      <View style={{ flex: 1 }}><TeamCell id={r.h} teams={teams} /></View>
      <View style={s.mMid}>
        <Text style={s.mScore}>{done ? `${r.s![0]} - ${r.s![1]}` : r.ko ? kickoffLocal(r.ko) : '—'}</Text>
        <Text style={s.mSub}>
          {done ? (r.p ? `ترجيح ${r.p[0]} - ${r.p[1]}` : STATUS_AR[r.st] || '')
            : r.st === 'PST' ? STATUS_AR.PST
            : when ? when.toLocaleDateString('ar', { day: 'numeric', month: 'short' }) : ''}
        </Text>
      </View>
      <View style={{ flex: 1 }}><TeamCell id={r.a} teams={teams} /></View>
    </View>
  );
}

export function MatchLine({ m, teams }: { m: MatchFull; teams: Teams }) {
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
  const rows = t.rows || [];
  return (
    <View style={s.mRow}>
      {/* aggregate line (tap = last leg, as before) */}
      <Pressable disabled={!leg} onPress={() => leg && onMatch(leg)}>
        <View style={s.mLine}>
          {side(t.home)}
          <View style={s.mMid}>
            <Text style={s.mScore}>{t.tbd || !t.agg ? '—' : `${t.agg.h} - ${t.agg.a}`}</Text>
            {t.pen ? <Text style={s.mSub}>ترجيح {t.pen.h} - {t.pen.a}</Text> : t.legs.length > 1 ? <Text style={s.mSub}>مجموع المباراتين</Text> : null}
          </View>
          {side(t.away)}
        </View>
      </Pressable>
      {/* legs (api ties[].rows): each with its own home team first; absent rows -> aggregate only */}
      {rows.map((r, k) => (
        <Pressable key={r.id} onPress={() => onMatch(r.id)} style={({ pressed }) => [s.legRow, pressed && s.legPressed]}>
          <Text style={s.legLbl}>{rows.length > 1 ? (k === 0 ? 'الذهاب' : k === 1 ? 'الإياب' : `مباراة ${k + 1}`) : 'المباراة'}</Text>
          <Text style={s.legTeams} numberOfLines={1}>{iso(teamName(teams[String(r.h)]))}</Text>
          <Text style={s.legScore}>{legText(r)}</Text>
          <Text style={[s.legTeams, s.legTeamsEnd]} numberOfLines={1}>{iso(teamName(teams[String(r.a)]))}</Text>
        </Pressable>
      ))}
    </View>
  );
}

// leg centre text: score (+ penalties) when played, else local kickoff (date + time) or the status label
function legText(r: Row) {
  const done = r.s && !['NS', 'TBD', 'PST'].includes(r.st);
  if (done) return `${r.s![0]} - ${r.s![1]}` + (r.p ? ` (${r.p[0]}-${r.p[1]})` : '');
  if (r.st === 'PST') return STATUS_AR.PST;
  if (r.ko) {
    const d = new Date(r.ko);
    return `${d.toLocaleDateString('ar', { day: 'numeric', month: 'short' })} ${kickoffLocal(r.ko)}`;
  }
  return r.date ? new Date(r.date + 'T00:00:00').toLocaleDateString('ar', { day: 'numeric', month: 'short' }) : '—';
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
  hl: { backgroundColor: '#e8f5ec' },
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
  link: { color: '#17803a' },
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
  legRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6, paddingVertical: 4, paddingHorizontal: 6,
            backgroundColor: '#f7f8f9', borderRadius: 6 },
  legPressed: { backgroundColor: '#eceef1' },
  legLbl: { width: 44, fontSize: 11, color: '#777', textAlign: 'right' },
  legTeams: { flex: 1, fontSize: 12, color: '#444', textAlign: 'right' },
  legTeamsEnd: { textAlign: 'left' },
  legScore: { minWidth: 70, fontSize: 12, fontWeight: '700', textAlign: 'center' },
  winner: { backgroundColor: '#e8f5ec', borderRadius: 6 },
  champ: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, backgroundColor: '#fff8e1' },
  champTx: { fontWeight: '700' },
});
