/**
 * Main application component
 */

import { AuthProvider, useAuth } from './context/AuthContext';
import { AppProvider } from './context/AppContext';
import { Layout } from './components/layout';
import { ChatContainer } from './components/chat';
import { LoginPage } from './components/auth';
import { Spinner } from './components/common';
import { useViewportHeight } from './hooks/useViewportHeight';

function AuthGate() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="h-app flex items-center justify-center bg-bg-900">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  // AppProvider hace polling de /health y /stats (protegidos) — solo se
  // monta dentro de la rama autenticada para no lanzar peticiones
  // protegidas antes de hacer login.
  return (
    <AppProvider>
      <Layout>
        <ChatContainer />
      </Layout>
    </AppProvider>
  );
}

function App() {
  useViewportHeight();

  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}

export default App;
