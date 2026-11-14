// Match screen: api/v1/matches/<id>.json (+ teams.json). Header, goals/cards timeline, lineups by position, stats bars.
// While live: worker / (score, minute, status) and /events?id= (timeline) every 30 s.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Image, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import {
  API, LIVE_CODES, LIVE_EVERY_MS, Live, LineupPlayer, MatchEvent, MatchFull, STATUS_AR, Score, Teams,
  absUrl, getJson, kickoffLocal, loadLive, loadLiveEvents, loadTeams, teamName,
} from './api';

const STAT_AR: Record<string, string> = {
  possession: 'الاستحواذ', shots_total: 'التسديدات', shots_on: 'على المرمى', shots_off: 'خارج المرمى',
  shots_blocked: 'تسديدات محجوبة', shots_inbox: 'من داخل المنطقة', shots_outbox: 'من خارج المنطقة',
  corners: 'الركنيات', offsides: 'التسلل', fouls: 'الأخطاء', yellow: 'البطاقات الصفراء', red: 'البطاقات الحمراء',
  saves: 'التصديات', passes_total: 'التمريرات', passes_ok: 'تمريرات صحيحة', passes_pct: 'دقة التمرير', xg: 'الأهداف المتوقعة',
};
const PCT = new Set(['possession', 'passes_pct']);
const POS_AR: Record<string, string> = { G: 'حراسة المرمى', D: 'الدفاع', M: 'الوسط', F: 'الهجوم' };
const POS_ORDER = ['G', 'D', 'M', 'F'];

// Same icons/labels as the site (make_matches.py CARD_ICON + goal_kind -> i18n.py "penalty"/"own_goal")
function evIcon(e: MatchEvent) {
  const d = (e.detail || '').toLowerCase();
  if (e.type === 'goal') return d.includes('missed') ? '❌' : '⚽';
  if (e.type === 'card') return d.includes('second') ? '🟨🟥' : d.includes('red') ? '🟥' : '🟨';
  return '';
}
function evKind(e: MatchEvent) {
  if (e.type !== 'goal') return '';
  const d = (e.detail || '').toLowerCase();
  if (d.includes('missed')) return 'ركلة جزاء ضائعة';
  if (d.includes('own')) return 'هدف عكسي';
  if (d.includes('penalty')) return 'ركلة جزاء';
  return '';
}
// "دور المجموعات - الجولة 4": drop empty parts so no stray " - "
function roundText(r?: { ar: string }) {
  return (r?.ar || '').split(' - ').map((x) => x.trim()).filter(Boolean).join(' - ');
}

export default function MatchScreen({ route }: NativeStackScreenProps<RootStack, 'Match'>) {
  const { id } = route.params;
  const [m, setM] = useState<MatchFull | null | undefined>(undefined);
  const [teams, setTeams] = useState<Teams>({});
  const [live, setLive] = useState<Live | undefined>();
  const [liveEv, setLiveEv] = useState<MatchEvent[] | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    const [mm, t] = await Promise.all([getJson<MatchFull>(`${API}/matches/${id}.json`), loadTeams()]);
    setM(mm);
    setTeams(t);
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const status = live?.s || m?.status || '';
  const isLive = LIVE_CODES.has(status);

  // live overlay: first check once; keep polling only while the feed lists it as live
  const pullLive = useCallback(async () => {
    if (!m) return;
    const l = await loadLive();
    const x = l?.[String(id)];
    if (x) setLive(x);
    if (x && LIVE_CODES.has(x.s || '')) {
      const ev = await loadLiveEvents(id, m.home, m.away);
      if (ev) setLiveEv(ev);
    }
  }, [m, id]);
  useEffect(() => {
    if (!m) return;
    pullLive();
    if (!isLive && !LIVE_CODES.has(m.status) && m.status !== 'NS') return;   // finished/postponed: one check is enough
    const t = setInterval(pullLive, LIVE_EVERY_MS);
    return () => clearInterval(t);
  }, [m, isLive, pullLive]);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    await pullLive();
    setRefreshing(false);
  }, [load, pullLive]);

  if (m === undefined) return <ActivityIndicator style={{ marginTop: 40 }} />;
  if (m === null) return <Text style={s.empty}>تعذّر تحميل المباراة</Text>;

  const score: Score | undefined = live && live.h != null ? { h: live.h, a: live.a ?? 0 } : m.score;
  const events = (liveEv && liveEv.length >= (m.events?.length || 0) ? liveEv : m.events || [])
    .filter((e) => e.type === 'goal' || e.type === 'card');
  const showScore = score && (isLive || !['NS', 'TBD', 'PST'].includes(status));
  const sub = isLive ? (status === 'HT' ? STATUS_AR.HT : live?.e != null ? `${live.e}'` : STATUS_AR[status] || status)
    : m.pen ? `ترجيح ${m.pen.h} - ${m.pen.a}` : STATUS_AR[status] || '';

  return (
    <ScrollView style={s.root} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
      {/* header */}
      <View style={s.head}>
        <HeadTeam id={m.home} teams={teams} />
        <View style={s.headMid}>
          <Text style={[s.bigScore, isLive && s.live]}>
            {showScore ? `${score!.h} - ${score!.a}` : kickoffLocal(m.kickoff)}
          </Text>
          {sub ? <Text style={[s.sub, isLive && s.live]}>{sub}</Text> : null}
          {roundText(m.round) ? <Text style={s.meta}>{roundText(m.round)}</Text> : null}
        </View>
        <HeadTeam id={m.away} teams={teams} />
      </View>
      {/* venue: Arabic only (api/v1 has English names today -> hidden) */}
      {m.venue?.name_ar ? <Text style={s.meta}>{[m.venue.name_ar, m.venue.city_ar].filter(Boolean).join('، ')}</Text> : null}

      {/* timeline */}
      {events.length ? (
        <Section title="الأحداث">
          {events.map((e, i) => (
            <View key={i} style={[s.ev, e.team === m.away && s.evAway]}>
              <Text style={s.evMin}>{e.minute}{e.extra ? `+${e.extra}` : ''}'</Text>
              <Text>{evIcon(e)}</Text>
              <Text style={s.evName} numberOfLines={1}>{e.player?.short?.ar || e.player?.name.ar || ''}</Text>
              {evKind(e) ? <Text style={s.evKind}>{evKind(e)}</Text> : null}
            </View>
          ))}
        </Section>
      ) : null}

      {/* lineups */}
      {m.lineups?.home && m.lineups?.away ? (
        <Section title="التشكيلتان">
          <View style={s.cols}>
            {(['home', 'away'] as const).map((side) => {
              const L = m.lineups![side]!;
              return (
                <View key={side} style={s.col}>
                  <Text style={s.colHead}>{teamName(teams[String(side === 'home' ? m.home : m.away)])}</Text>
                  {L.formation ? <Text style={s.meta}>{L.formation}</Text> : null}
                  {POS_ORDER.map((p) => {
                    const ps = L.start.filter((x) => (x.pos || '').toUpperCase().startsWith(p));
                    return ps.length ? (
                      <View key={p}>
                        <Text style={s.pos}>{POS_AR[p]}</Text>
                        {ps.map((x, i) => <PlayerLine key={i} x={x} />)}
                      </View>
                    ) : null;
                  })}
                  {L.subs?.length ? (
                    <View>
                      <Text style={s.pos}>البدلاء</Text>
                      {L.subs.map((x, i) => <PlayerLine key={i} x={x} />)}
                    </View>
                  ) : null}
                  {L.coach ? <Text style={s.meta}>المدرب: {L.coach.name.ar}</Text> : null}
                </View>
              );
            })}
          </View>
        </Section>
      ) : null}

      {/* stats */}
      {m.stats && Object.keys(m.stats).length ? (
        <Section title="الإحصائيات">
          {Object.entries(m.stats).map(([k, v]) => <StatBar key={k} k={k} v={v} />)}
        </Section>
      ) : null}
      <View style={{ height: 30 }} />
    </ScrollView>
  );
}

function HeadTeam({ id, teams }: { id: number; teams: Teams }) {
  const t = teams[String(id)];
  const logo = absUrl(t?.logo);
  return (
    <View style={s.headTeam}>
      {logo ? <Image source={{ uri: logo }} style={s.headLogo} /> : <View style={s.headLogo} />}
      <Text style={s.headName} numberOfLines={2}>{teamName(t)}</Text>
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={s.sec}>
      <Text style={s.secTx}>{title}</Text>
      {children}
    </View>
  );
}

function PlayerLine({ x }: { x: LineupPlayer }) {
  return (
    <Text style={s.pl} numberOfLines={1}>
      {x.number != null ? `${x.number}  ` : ''}{x.player.short?.ar || x.player.name.ar}
    </Text>
  );
}

function StatBar({ k, v }: { k: string; v: Score }) {
  const h = Number(v.h) || 0;
  const a = Number(v.a) || 0;
  const tot = h + a || 1;
  const fmt = (n: number) => (PCT.has(k) ? `${n}%` : String(n));
  return (
    <View style={s.stat}>
      <View style={s.statTop}>
        <Text style={s.statVal}>{fmt(h)}</Text>
        <Text style={s.statLbl}>{STAT_AR[k] || k}</Text>
        <Text style={s.statVal}>{fmt(a)}</Text>
      </View>
      <View style={s.bar}>
        <View style={[s.barH, { flex: h / tot }]} />
        <View style={[s.barA, { flex: a / tot }]} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  // direction rtl: home on the RIGHT whatever the phone language (Expo Go ignores I18nManager.forceRTL)
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl' },
  empty: { textAlign: 'center', marginTop: 40, color: '#777' },
  pl: { fontSize: 13, paddingVertical: 2, textAlign: 'right' },
  head: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, paddingTop: 16, paddingBottom: 6 },
  headTeam: { flex: 1, alignItems: 'center', gap: 6 },
  headLogo: { width: 52, height: 52, resizeMode: 'contain' },
  headName: { fontSize: 15, fontWeight: '600', textAlign: 'center' },
  headMid: { width: 110, alignItems: 'center' },
  bigScore: { fontSize: 26, fontWeight: '800' },
  sub: { fontSize: 12, color: '#666', marginTop: 2 },
  meta: { fontSize: 12, color: '#777', textAlign: 'center', marginTop: 2 },
  live: { color: '#c62828' },
  sec: { marginTop: 16, paddingHorizontal: 12 },
  secTx: { fontSize: 15, fontWeight: '700', marginBottom: 8, backgroundColor: '#f2f3f5', padding: 6 },
  ev: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
  evAway: { flexDirection: 'row-reverse' },
  evMin: { width: 40, fontWeight: '700', color: '#444', textAlign: 'center' },
  evName: { flexShrink: 1, fontSize: 14 },
  evKind: { fontSize: 12, color: '#777' },
  cols: { flexDirection: 'row', gap: 10 },
  col: { flex: 1 },
  colHead: { fontWeight: '700', textAlign: 'center' },
  pos: { fontSize: 12, color: '#17803a', fontWeight: '700', marginTop: 8, marginBottom: 2 },
  stat: { marginBottom: 10 },
  statTop: { flexDirection: 'row', justifyContent: 'space-between' },
  statVal: { fontWeight: '700', width: 50, textAlign: 'center' },
  statLbl: { color: '#555', fontSize: 13 },
  bar: { flexDirection: 'row', height: 6, borderRadius: 3, overflow: 'hidden', backgroundColor: '#eee', marginTop: 4, gap: 2 },
  barH: { backgroundColor: '#17803a' },
  barA: { backgroundColor: '#1565c0' },
});
