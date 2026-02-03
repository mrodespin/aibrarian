/**
 * Main application component
 */

import { AppProvider } from './context/AppContext';
import { Layout } from './components/layout';
import { ChatContainer } from './components/chat';

function App() {
  return (
    <AppProvider>
      <Layout>
        <ChatContainer />
      </Layout>
    </AppProvider>
  );
}

export default App;
