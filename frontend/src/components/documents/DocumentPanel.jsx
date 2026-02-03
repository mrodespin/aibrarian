/**
 * Document management panel
 */

import { SyncForm } from './SyncForm';

export function DocumentPanel() {
  return (
    <div className="space-y-4">
      <SyncForm />

      {/* Future: Document list could go here */}
      {/* <DocumentList /> */}
    </div>
  );
}

export default DocumentPanel;
