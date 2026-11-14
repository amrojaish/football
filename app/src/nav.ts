// Navigation helpers shared by screens.
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useCallback } from 'react';
import type { RootStack } from '../App';

// Real provider ids are > 0 (lineups use negative placeholder ids for players without one)
export const hasPlayerId = (id?: number | null): id is number => typeof id === 'number' && id > 0;

export function useOpenPlayer() {
  const nav = useNavigation<NativeStackNavigationProp<RootStack>>();
  return useCallback((id?: number | null, name?: string) => {
    if (hasPlayerId(id)) nav.push('Player', { id, name });
  }, [nav]);
}
