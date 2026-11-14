// Matches list: Yesterday / Today / Tomorrow from api/v1/days/<date>.json, grouped by competition, live overlay every 30 s.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Image, Pressable, RefreshControl, SectionList, StyleSheet, Text, View,
} from 'react-native';
import type { RootStack } from '../App';
import {
  API, Comp, DayMatch, LIVE_CODES, LIVE_EVERY_MS, Live, STATUS_AR, Teams, absUrl, getJson,
  kickoffLocal, loadLive, loadTeams, teamName,
} from './api';

function ymd(d: Date) {   // device-local calendar day, same as the site's day panels
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}
function dayOffset(off: number) {
  const d = new Date();
  d.setDate(d.getDate() + off);
  return d;
}

const TABS = [{ off: -1, label: 'أمس' }, { off: 0, label: 'اليوم' }, { off: 1, label: 'غداً' }];

export default function MatchesScreen({ navigation }: NativeStackScreenProps<RootStack, 'Matches'>) {
  const [tab, setTab] = useState(1);
  const [teams, setTeams] = useState<Teams>({});
  const [comps, setComps] = useState<Comp[]>([]);
  const [matches, setMatches] = useState<DayMatch[] | null>(null);
  const [live, setLive] = useState<Record<string, Live>>({});
  const [err, setErr] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    (async () => {
      const [t, idx] = await Promise.all([
        loadTeams(),
        getJson<{ leagues?: Comp[]; cups?: Comp[] }>(API + '/index.json'),
      ]);
      setTeams(t);
      // cups[] carry type ('cup'); tag them so the header opens the cup screen
      if (idx) setComps([...(idx.leagues || []), ...(idx.cups || []).map((c) => ({ ...c, type: c.type || 'cup' }))]);
      if (!Object.keys(t).length) setErr('تعذّر تحميل الفرق');
    })();
  }, []);

  // A day missing from api/v1 (outside the build window) = no matches, not an error
  const loadDay = useCallback(async (date: string) => {
    const d = await getJson<DayMatch[]>(`${API}/days/${date}.json`);
    setMatches(d || []);
  }, []);

  const date = ymd(dayOffset(TABS[tab].off));
  useEffect(() => {
    setMatches(null);
    loadDay(date);
  }, [date, loadDay]);

  const pullLive = useCallback(async () => {
    const l = await loadLive();
    if (l) setLive(l);
  }, []);
  useEffect(() => {
    pullLive();
    const t = setInterval(pullLive, LIVE_EVERY_MS);
    return () => clearInterval(t);
  }, [pullLive]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await Promise.all([loadDay(date), pullLive()]);
    setRefreshing(false);
  }, [date, loadDay, pullLive]);

  const sections = useMemo(() => {
    if (!matches) return [];
    const order = new Map(comps.map((c, i) => [c.code, i]));
    const by = new Map<string, DayMatch[]>();
    for (const m of matches) {
      if (!by.has(m.league)) by.set(m.league, []);
      by.get(m.league)!.push(m);
    }
    return [...by.entries()]
      .sort((a, b) => (order.get(a[0]) ?? 999) - (order.get(b[0]) ?? 999))
      .map(([code, data]) => {
        const c = comps.find((x) => x.code === code);
        return { code, title: c?.name.ar || code, logo: absUrl(c?.logo), cup: !!c?.type,
                 data: data.sort((a, b) => a.kickoff.localeCompare(b.kickoff)) };
      });
  }, [matches, comps]);

  return (
    <View style={s.root}>
      <View style={s.tabs}>
        {TABS.map((t, i) => (
          <Pressable key={t.off} onPress={() => setTab(i)} style={[s.tab, i === tab && s.tabOn]}>
            <Text style={[s.tabTx, i === tab && s.tabTxOn]}>{t.label}</Text>
          </Pressable>
        ))}
      </View>
      {err ? <Text style={s.err}>{err}</Text> : null}
      {matches === null ? (
        <ActivityIndicator style={{ marginTop: 40 }} />
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(m) => String(m.id)}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
          ListEmptyComponent={<Text style={s.empty}>لا مباريات</Text>}
          renderSectionHeader={({ section }) => (
            <Pressable onPress={() => navigation.navigate('Competition', { code: section.code, cup: section.cup })}
                       style={s.secHead}>
              {section.logo ? <Image source={{ uri: section.logo }} style={s.secLogo} /> : null}
              <Text style={s.secTx}>{section.title}</Text>
              <Text style={s.secMore}>‹</Text>
            </Pressable>
          )}
          renderItem={({ item }) => (
            <Pressable onPress={() => navigation.navigate('Match', { id: item.id })}
                       style={({ pressed }) => pressed && s.pressed}>
              <Row m={item} teams={teams} live={live[String(item.id)]} />
            </Pressable>
          )}
          stickySectionHeadersEnabled
        />
      )}
    </View>
  );
}

function Row({ m, teams, live }: { m: DayMatch; teams: Teams; live?: Live }) {
  const status = live?.s || m.status;
  const isLive = LIVE_CODES.has(status);
  const score = live && live.h != null ? { h: live.h, a: live.a ?? 0 } : m.score;

  let center: string;
  let sub = '';
  if (isLive) {
    center = score ? `${score.h} - ${score.a}` : '0 - 0';
    sub = status === 'HT' ? STATUS_AR.HT : live?.e != null ? `${live.e}'` : status;
  } else if (score && status !== 'NS' && status !== 'TBD' && status !== 'PST') {
    center = `${score.h} - ${score.a}`;
    sub = m.pen ? `ترجيح ${m.pen.h} - ${m.pen.a}` : STATUS_AR[status] || '';
  } else {
    center = kickoffLocal(m.kickoff);
    sub = STATUS_AR[status] || '';
  }

  return (
    <View style={s.row}>
      <Side id={m.home} teams={teams} />
      <View style={s.mid}>
        <Text style={[s.score, isLive && s.live]}>{center}</Text>
        {sub ? <Text style={[s.sub, isLive && s.live]}>{sub}</Text> : null}
      </View>
      <Side id={m.away} teams={teams} end />
    </View>
  );
}

function Side({ id, teams, end }: { id: number; teams: Teams; end?: boolean }) {
  const team = teams[String(id)];
  const logo = absUrl(team?.logo);
  return (
    <View style={[s.side, end && s.sideEnd]}>
      {logo ? <Image source={{ uri: logo }} style={s.logo} /> : <View style={s.logo} />}
      <Text style={s.name} numberOfLines={2}>{teamName(team)}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  // direction rtl: home on the RIGHT whatever the phone language (Expo Go ignores I18nManager.forceRTL)
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderColor: '#ddd' },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabOn: { borderBottomWidth: 2, borderColor: '#17803a' },
  tabTx: { fontSize: 15, color: '#555' },
  tabTxOn: { color: '#17803a', fontWeight: '700' },
  err: { color: '#c62828', textAlign: 'center', padding: 8 },
  empty: { textAlign: 'center', marginTop: 40, color: '#777' },
  secHead: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: '#f2f3f5', paddingHorizontal: 12, paddingVertical: 8 },
  secLogo: { width: 20, height: 20, resizeMode: 'contain' },
  secTx: { fontWeight: '700', fontSize: 14, flex: 1, textAlign: 'right' },
  secMore: { fontSize: 18, color: '#999' },
  pressed: { backgroundColor: '#f5f5f5' },
  row: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: '#e5e5e5' },
  side: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 },
  sideEnd: { flexDirection: 'row-reverse' },
  logo: { width: 24, height: 24, resizeMode: 'contain' },
  name: { flexShrink: 1, fontSize: 14, textAlign: 'right' },
  mid: { width: 76, alignItems: 'center' },
  score: { fontSize: 15, fontWeight: '700' },
  sub: { fontSize: 11, color: '#666', marginTop: 2 },
  live: { color: '#c62828' },
});
