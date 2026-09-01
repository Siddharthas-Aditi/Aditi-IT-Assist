/** Change-template lifecycle is deferred until it has a backend contract. */

import { PageHeader } from "../components/chrome";
import { EmptyState, Panel } from "../components/ui";

export function ChangeTemplatesPage() {
  return (
    <div className="space-y-4 pb-10">
      <PageHeader
        title="Change Templates"
        crumbs={[{ label: "Changes", to: "/itsm/changes" }, { label: "Templates" }]}
        description="Reusable Change defaults."
      />
      <Panel title="Templates unavailable">
        <EmptyState
          title="Server-backed templates are not available yet"
          description="This UI intentionally does not create browser-only templates. Add a backend template contract before enabling create, clone, archive, or edit actions."
        />
      </Panel>
    </div>
  );
}
