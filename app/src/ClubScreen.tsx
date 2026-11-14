// Club screen (M3): api/v1/teams/<id>.json. Header (logo, Arabic name, league + standing) and tabs:
// Matches (last 10 results newest first + next 5, fetched lazily) | Table (club's league, row highlighted) | Squad (by position).
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import { API, Comp, MatchFull, Name, Teams, absUrl, getJson, loadTeams } from './api';
import { League, MatchLine, Table, loadMatch } from './CompetitionScreen';

type SquadPlayer = { player?: { id?: number; name: Name; short?: Name }; number?: number; pos?: string; pos_code?: string; apps?: number };
type Club = {
  id: number; name: Name; short?: Name; logo?: string; color?: string; league?: string; season?: number;
  venue?: { name?: string; city?: string; capacity?: number };
  coach?: { name: Name; age?: number; nationality?: string };
  standing?: { rank: number; pts: number; played: number };
  squad?: SquadPlayer[];
  matches?: { results?: number[]; upcoming?: number[] };
};

const N_RESULTS = 10;
const N_UPCOMING = 5;
const POS_AR: Record<string, string> = { G: 'حراسة المرمى', D: 'الدفاع', M: 'الوسط', F: 'الهجوم' };
const POS_ORDER = ['G', 'D', 'M', 'F'];

export default function ClubScreen({ route, navigation }: NativeStackScreenProps<RootStack, 'Club'>) {
  const { id } = route.params;
  const [club, setClub] = useState<Club | null | undefined>(undefined);
  const [teams, setTeams] = useState<Teams>({});
  const [leagueName, setLeagueName] = useState<string>('');
  const [tab, setTab] = useState(0);

  useEffect(() => {
    loadTeams().then((t) => {
      setTeams(t);
      if (t[String(id)]) navigation.setOptions({ title: t[String(id)].name.ar });
    });
    getJson<Club>(`${API}/teams/${id}.json`).then(setClub);
  }, [id, navigation]);

  useEffect(() => {
    if (!club?.league) return;
    getJson<{ leagues?: Comp[] }>(API + '/index.json').then((idx) => {
      const c = idx?.leagues?.find((x) => x.code === club.league);
      if (c) setLeagueName(c.name.ar);
    });
  }, [club?.league]);

  const t = teams[String(id)];
  const logo = absUrl(club?.logo || t?.logo);
  const name = club?.name.ar || t?.name.ar || '';
  const openMatch = (mid: number) => navigation.push('Match', { id: mid });
  const openTeam = (tid: number) => tid !== id && navigation.push('Club', { id: tid });
  const openLeague = () => club?.league && navigation.push('Competition', { code: club.league });

  const tabs: { label: string; body: () => React.ReactNode }[] = [];
  if (club) {
    tabs.push({ label: 'المباريات', body: () => <ClubMatches club={club} teams={teams} onMatch={openMatch} /> });
    if (club.league) tabs.push({ label: 'الترتيب', body: () => (
      <ClubTable code={club.league!} id={id} teams={teams} onTeam={openTeam} onLeague={openLeague} leagueName={leagueName} />
    ) });
    if (club.squad?.length) tabs.push({ label: 'اللاعبون', body: () => <Squad club={club} /> });
  }
  const cur = Math.min(tab, Math.max(0, tabs.length - 1));

  return (
    <View style={s.root}>
      <View style={[s.head, club?.color ? { borderBottomColor: club.color } : null]}>
        {logo ? <Image source={{ uri: logo }} style={s.logo} /> : <View style={s.logo} />}
        <View style={{ flex: 1 }}>
          <Text style={s.name}>{name}</Text>
          {club?.league ? (
            <Pressable onPress={openLeague}>
              <Text style={s.meta}>
                {leagueName || club.league}
                {club.standing ? ` · المركز ${club.standing.rank} · ${club.standing.pts} نقطة` : ''}
              </Text>
            </Pressable>
          ) : null}
          {club?.coach ? (
            <Text style={[s.meta, s.coachLine]}>{'المدرب: \u2068' + club.coach.name.ar + '\u2069'}</Text>
          ) : null}
        </View>
      </View>
      {club === undefined ? <ActivityIndicator style={{ marginTop: 40 }} /> : club === null ? (
        <Text style={s.empty}>لا بيانات لهذا النادي</Text>
      ) : (
        <>
          <View style={s.tabs}>
            {tabs.map((x, i) => (
              <Pressable key={x.label} onPress={() => setTab(i)} style={[s.tab, i === cur && s.tabOn]}>
                <Text style={[s.tabTx, i === cur && s.tabTxOn]}>{x.label}</Text>
              </Pressable>
            ))}
          </View>
          <View style={{ flex: 1 }}>{tabs[cur]?.body()}</View>
        </>
      )}
    </View>
  );
}

function ClubMatches({ club, teams, onMatch }: { club: Club; teams: Teams; onMatch: (id: number) => void }) {
  // results are oldest-first in the JSON -> newest N first; upcoming are soonest-first
  const resIds = (club.matches?.results || []).slice(-N_RESULTS).reverse();
  const upIds = (club.matches?.upcoming || []).slice(0, N_UPCOMING);
  const [res, setRes] = useState<(MatchFull | null)[] | null>(null);
  const [up, setUp] = useState<(MatchFull | null)[] | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all(upIds.map(loadMatch)).then((r) => live && setUp(r));
    Promise.all(resIds.map(loadMatch)).then((r) => live && setRes(r));
    return () => { live = false; };
  }, [club.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const list = (ids: number[], ms: (MatchFull | null)[] | null) =>
    ms === null ? <ActivityIndicator style={{ margin: 20 }} /> : ids.map((mid, i) => (
      <Pressable key={mid} onPress={() => onMatch(mid)} style={s.mRow}>
        {ms[i] ? <MatchLine m={ms[i]!} teams={teams} /> : <Text style={s.empty}>مباراة {mid}</Text>}
      </Pressable>
    ));
  if (!resIds.length && !upIds.length) return <Text style={s.empty}>لا مباريات</Text>;
  return (
    <ScrollView>
      {upIds.length ? <Text style={s.secHead}>القادمة</Text> : null}
      {list(upIds, up)}
      {resIds.length ? <Text style={s.secHead}>النتائج الأخيرة</Text> : null}
      {list(resIds, res)}
    </ScrollView>
  );
}

function ClubTable({ code, id, teams, onTeam, onLeague, leagueName }: {
  code: string; id: number; teams: Teams; onTeam: (id: number) => void; onLeague: () => void; leagueName: string;
}) {
  const [lg, setLg] = useState<League | null | undefined>(undefined);
  useEffect(() => { getJson<League>(`${API}/leagues/${code}.json`).then(setLg); }, [code]);
  if (lg === undefined) return <ActivityIndicator style={{ marginTop: 30 }} />;
  if (!lg?.table?.length) return <Text style={s.empty}>لا جدول</Text>;
  return (
    <View style={{ flex: 1 }}>
      <Pressable onPress={onLeague} style={s.leagueLink}>
        <Text style={s.leagueLinkTx}>{leagueName || lg.name.ar}</Text>
        <Text style={s.more}>‹</Text>
      </Pressable>
      <Table rows={lg.table} teams={teams} onTeam={onTeam} highlight={id} />
    </View>
  );
}

function Squad({ club }: { club: Club }) {
  const sq = club.squad || [];
  const other = sq.filter((p) => !POS_ORDER.includes(p.pos_code || ''));
  return (
    <ScrollView>
      {POS_ORDER.map((pc) => {
        const ps = sq.filter((p) => p.pos_code === pc);
        return ps.length ? (
          <View key={pc}>
            <Text style={s.secHead}>{POS_AR[pc]}</Text>
            {ps.map((p, i) => <PlayerRow key={i} p={p} />)}
          </View>
        ) : null;
      })}
      {other.length ? (
        <View>
          <Text style={s.secHead}>آخرون</Text>
          {other.map((p, i) => <PlayerRow key={i} p={p} />)}
        </View>
      ) : null}
    </ScrollView>
  );
}

function PlayerRow({ p }: { p: SquadPlayer }) {
  return (
    <View style={s.pRow}>
      <Text style={s.pNum}>{p.number ?? ''}</Text>
      <Text style={s.pName} numberOfLines={1}>{p.player?.short?.ar || p.player?.name.ar || '—'}</Text>
      <Text style={s.pApps}>{`${p.apps ?? 0} مباراة`}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  empty: { textAlign: 'center', marginTop: 30, color: '#777' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderBottomWidth: 3, borderBottomColor: '#eee' },
  logo: { width: 64, height: 64, resizeMode: 'contain' },
  name: { fontSize: 20, fontWeight: '700', textAlign: 'right' },
  // one Text + FSI/PDI isolates around the (often Latin) name: label stays first in RTL
  coachLine: { writingDirection: 'rtl', textAlign: 'right', alignSelf: 'stretch' },
  meta: { fontSize: 13, color: '#666', marginTop: 3, textAlign: 'right' },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderColor: '#ddd' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabOn: { borderBottomWidth: 2, borderColor: '#17803a' },
  tabTx: { fontSize: 15, color: '#555' },
  tabTxOn: { color: '#17803a', fontWeight: '700' },
  secHead: { fontWeight: '700', backgroundColor: '#f2f3f5', padding: 8, textAlign: 'right' },
  mRow: { borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5', paddingVertical: 10, paddingHorizontal: 8 },
  leagueLink: { flexDirection: 'row', alignItems: 'center', padding: 10, backgroundColor: '#f2f3f5' },
  leagueLinkTx: { flex: 1, fontWeight: '700', textAlign: 'right' },
  more: { fontSize: 18, color: '#999' },
  pRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, paddingHorizontal: 10,
          borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5' },
  pNum: { width: 30, textAlign: 'center', fontWeight: '700', color: '#555' },
  pName: { flex: 1, fontSize: 14, textAlign: 'right' },
  pApps: { width: 72, marginStart: 12, fontSize: 12, color: '#777', textAlign: 'left' },
});
