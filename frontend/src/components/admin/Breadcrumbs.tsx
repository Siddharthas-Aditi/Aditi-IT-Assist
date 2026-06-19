/**
 * Breadcrumb trail for the Admin Console.
 *
 * Complements browser back navigation — every deep admin page (detail, edit,
 * create, review, queue/ticket detail) renders one so an admin always knows
 * where they are and can climb back up the route tree in one click.
 *
 * The last crumb is the current page (rendered as plain text, never a link).
 */

import { Link } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';

export interface Crumb {
  label: string;
  /** Omit `to` for the current (last) crumb. */
  to?: string;
}

interface BreadcrumbsProps {
  items: Crumb[];
  className?: string;
  /** Where the home icon links to. Defaults to the admin dashboard. */
  homeTo?: string;
}

export function Breadcrumbs({ items, className, homeTo = '/dashboard' }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className={className}>
      <ol className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
        <li className="flex items-center">
          <Link
            to={homeTo}
            className="flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:text-foreground"
          >
            <Home size={13} />
            <span className="sr-only">Admin home</span>
          </Link>
        </li>
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`} className="flex items-center gap-1">
              <ChevronRight size={13} className="text-border" aria-hidden />
              {item.to && !isLast ? (
                <Link
                  to={item.to}
                  className="rounded px-1 py-0.5 transition-colors hover:text-foreground"
                >
                  {item.label}
                </Link>
              ) : (
                <span
                  className="px-1 py-0.5 font-medium text-foreground"
                  aria-current={isLast ? 'page' : undefined}
                >
                  {item.label}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
