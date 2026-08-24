export type AuthUser = {
  id: string;
  email: string;
  name: string;
  roles: string[];
};

const STORAGE_KEY = 'sales-agent-auth';

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function loginWithEmail(email: string, password: string): AuthUser {
  const normalizedEmail = email.trim();
  if (!normalizedEmail || !normalizedEmail.includes('@')) {
    throw new Error('Please provide a valid email address.');
  }

  if (!password || password.length < 6) {
    throw new Error('Password must be at least 6 characters long.');
  }

  const user: AuthUser = {
    id: 'user-1',
    email: normalizedEmail,
    name: normalizedEmail.split('@')[0].replace(/[._-]/g, ' '),
    roles: ['admin'],
  };

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  }

  return user;
}

export function logoutUser(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(STORAGE_KEY);
  }
}

export function isAuthenticated(): boolean {
  return Boolean(getStoredUser());
}
