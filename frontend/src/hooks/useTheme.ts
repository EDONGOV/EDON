import { useEffect, useState } from 'react';

type Theme = 'dark' | 'light';
const STORAGE_KEY = 'edon_theme';

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.classList.remove('dark', 'light');
  root.classList.add(theme);
  localStorage.setItem(STORAGE_KEY, theme);
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'dark';
    return (localStorage.getItem(STORAGE_KEY) as Theme) ?? 'dark';
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
  };

  const toggleTheme = () => {
    setThemeState((t) => (t === 'dark' ? 'light' : 'dark'));
  };

  return { theme, setTheme, toggleTheme };
}
