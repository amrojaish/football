// Club screen placeholder (M2): name + logo only, from teams.json.
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import type { RootStack } from '../App';
import { Team, absUrl, loadTeams } from './api';

export default function ClubScreen({ route, navigation }: NativeStackScreenProps<RootStack, 'Club'>) {
  const { id } = route.params;
  const [t, setT] = useState<Team | undefined>();
  useEffect(() => {
    loadTeams().then((all) => {
      const x = all[String(id)];
      setT(x);
      if (x) navigation.setOptions({ title: x.name.ar });
    });
  }, [id, navigation]);
  const logo = absUrl(t?.logo);
  return (
    <View style={s.root}>
      {logo ? <Image source={{ uri: logo }} style={s.logo} /> : null}
      <Text style={s.name}>{t ? t.name.ar : '…'}</Text>
      <Text style={s.note}>صفحة النادي قريباً</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#fff', direction: 'rtl', alignItems: 'center', paddingTop: 40, gap: 12 },
  logo: { width: 96, height: 96, resizeMode: 'contain' },
  name: { fontSize: 22, fontWeight: '700' },
  note: { color: '#777' },
});
