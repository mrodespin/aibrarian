/**
 * Login page — shown when there's no active session
 */

import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { Card, Input, Button, Alert, Spinner } from '../common';

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login(email, password);
    } catch (err) {
      setError(err.message || 'Login failed');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="h-app flex items-center justify-center bg-bg-900 px-4">
      <Card title="📚 AIbrarian" className="w-full max-w-sm">
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={isLoading}
            autoFocus
          />
          <Input
            label="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={isLoading}
          />

          {error && <Alert type="error">{error}</Alert>}

          <Button type="submit" disabled={isLoading} className="w-full">
            {isLoading ? (
              <>
                <Spinner size="sm" className="mr-2" />
                Logging in...
              </>
            ) : (
              'Log in'
            )}
          </Button>
        </form>
      </Card>
    </div>
  );
}

export default LoginPage;
