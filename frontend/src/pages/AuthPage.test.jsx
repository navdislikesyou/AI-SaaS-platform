/**
 * Tests for the sign-in screen.
 *
 * The screen used to offer demo accounts and a Google SSO button, neither of
 * which the backend implements. These tests assert that a failed sign-in
 * reports the real reason, that an unreachable server is not presented as a
 * successful sign-in, and that the demo shortcuts are gone.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AuthPage from './AuthPage';

const auth = vi.hoisted(() => ({
  login: vi.fn(),
}));

vi.mock('../context/AuthContext', () => ({
  useAuth: () => auth,
}));

vi.mock('framer-motion', async () => {
  const ReactModule = await import('react');

  // The animation props are dropped: they are not valid DOM attributes and
  // React would warn about every one of them.
  const ANIMATION_PROPS = new Set([
    'initial',
    'animate',
    'exit',
    'transition',
    'whileHover',
    'whileTap',
    'variants',
  ]);

  const createComponent = (tag) => {
    const Component = ReactModule.forwardRef(({ children, ...props }, ref) => {
      const domProps = {};
      for (const [key, value] of Object.entries(props)) {
        if (!ANIMATION_PROPS.has(key)) {
          domProps[key] = value;
        }
      }
      return ReactModule.createElement(tag, { ref, ...domProps }, children);
    });
    Component.displayName = `motion.${tag}`;
    return Component;
  };

  // The component for a tag has to be stable. Building a new one on every
  // property access would give React a different component type on every
  // render, and it would remount the whole subtree each time.
  const cache = new Map();
  const stable = (tag) => {
    if (!cache.has(tag)) {
      cache.set(tag, createComponent(tag));
    }
    return cache.get(tag);
  };

  return {
    motion: new Proxy({}, { get: (_target, tag) => stable(tag) }),
    AnimatePresence: ({ children }) => children,
    useAnimationFrame: () => {},
  };
});

describe('AuthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('signs in with the email and password that were typed', async () => {
    auth.login.mockResolvedValue({ id: 'user-1' });
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/authorizing" element={<div>Authorizing</div>} />
        </Routes>
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/email address/i), 'aarti@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(auth.login).toHaveBeenCalledWith('aarti@example.com', 'secret'));
  });

  it('reports the backend reason for a rejected sign-in', async () => {
    const error = Object.assign(new Error('Invalid email or password.'), { status: 401 });
    auth.login.mockRejectedValue(error);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/email address/i), 'aarti@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'wrong');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
  });

  it('reports an unreachable server instead of pretending to sign in', async () => {
    const error = Object.assign(new Error('Network request failed'), { status: 0 });
    auth.login.mockRejectedValue(error);
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/email address/i), 'aarti@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/cannot reach the server/i)).toBeInTheDocument();
  });

  it('does not submit without both fields', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    await user.type(screen.getByLabelText(/email address/i), 'aarti@example.com');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(auth.login).not.toHaveBeenCalled();
    expect(await screen.findByText(/enter your credentials/i)).toBeInTheDocument();
  });

  it('offers no demo accounts', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    expect(screen.queryByText(/demo accounts/i)).not.toBeInTheDocument();
    expect(screen.queryByText('Owner')).not.toBeInTheDocument();
    expect(screen.queryByText('HR Admin')).not.toBeInTheDocument();
  });

  it('offers no single sign-on the backend does not implement', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    expect(screen.queryByText(/google sso/i)).not.toBeInTheDocument();
  });

  it('offers no remember-me option, because the access token is not persisted', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    expect(screen.queryByText(/remember me/i)).not.toBeInTheDocument();
  });

  it('offers no password reset, because the backend does not implement one', () => {
    render(
      <MemoryRouter initialEntries={['/login']}>
        <AuthPage />
      </MemoryRouter>
    );

    expect(screen.queryByText(/forgot password/i)).not.toBeInTheDocument();
  });
});
