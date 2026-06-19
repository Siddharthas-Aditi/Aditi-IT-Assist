/**
 * Standard page header for every Admin Console screen.
 *
 * Renders an optional breadcrumb trail, a title + purpose line, and a slot for
 * page-level actions (buttons, filters). Using one component everywhere keeps
 * spacing, typography, and hierarchy consistent across the admin experience.
 */

import { type ReactNode } from 'react';
import { Breadcrumbs, type Crumb } from './Breadcrumbs';

interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumbs?: Crumb[];
  /** Where the breadcrumb home icon links. Defaults to the admin dashboard. */
  breadcrumbHome?: string;
  /** Right-aligned actions (buttons, refresh, etc.). */
  actions?: ReactNode;
  /** Optional content rendered below the header row (e.g. a sub-tab bar). */
  children?: ReactNode;
}

export function PageHeader({
  title,
  description,
  breadcrumbs,
  breadcrumbHome,
  actions,
  children,
}: PageHeaderProps) {
  return (
    <header className="border-b border-border bg-card">
      <div className="px-6 pb-4 pt-5">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <Breadcrumbs items={breadcrumbs} homeTo={breadcrumbHome} className="mb-3" />
        )}
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">
              {title}
            </h1>
            {description && (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
        {children && <div className="mt-4">{children}</div>}
      </div>
    </header>
  );
}
