// Saffara app: native stack (Matches list -> Match). RTL is forced once (applies after the next JS reload).
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { StatusBar } from 'expo-status-bar';
import { I18nManager } from 'react-native';
import MatchesScreen from './src/MatchesScreen';
import MatchScreen from './src/MatchScreen';
import CompetitionScreen from './src/CompetitionScreen';
import ClubScreen from './src/ClubScreen';

if (!I18nManager.isRTL) {
  I18nManager.allowRTL(true);
  I18nManager.forceRTL(true);
}

export type RootStack = {
  Matches: undefined;
  Match: { id: number };
  Competition: { code: string; cup?: boolean };
  Club: { id: number };
};

const Stack = createNativeStackNavigator<RootStack>();

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="auto" />
      <Stack.Navigator>
        <Stack.Screen name="Matches" component={MatchesScreen} options={{ title: 'المباريات' }} />
        <Stack.Screen name="Match" component={MatchScreen} options={{ title: 'المباراة' }} />
        <Stack.Screen name="Competition" component={CompetitionScreen} options={{ title: 'البطولة' }} />
        <Stack.Screen name="Club" component={ClubScreen} options={{ title: 'النادي' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
