/**
 * Document management panel
 */

import { SyncForm } from './SyncForm';
import { DocumentList } from './DocumentList';

export function DocumentPanel() {
  return (
    <div className="space-y-4">
      <SyncForm />
      <DocumentList />
    </div>
  );
}

export default DocumentPanel;
