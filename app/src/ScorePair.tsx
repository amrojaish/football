// Score as two cells in the row's own direction: the home number sits beside the home team (first child = start side,
// right in RTL). A single "3 - 0" string is laid out LTR by the text engine (it starts with a digit) and mirrors the sides.
import { StyleSheet, Text, View } from 'react-native';
import type { StyleProp, TextStyle } from 'react-native';

export default function ScorePair({ h, a, style }: { h: number; a: number; style?: StyleProp<TextStyle> }) {
  return (
    <View style={s.pair}>
      <Text style={style}>{h}</Text>
      <Text style={style}>-</Text>
      <Text style={style}>{a}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  pair: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 },
});
