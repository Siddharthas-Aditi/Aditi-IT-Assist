import { Bell, User } from 'lucide-react';

export function TopBar() {
  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-card px-6">
      <div className="flex items-center gap-4">
        <h2 className="text-lg font-semibold text-foreground">IT Support</h2>
      </div>
      <div className="flex items-center gap-4">
        <button className="relative rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-destructive" />
        </button>
        <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-1.5">
          <User className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm text-foreground">Employee</span>
        </div>
      </div>
    </header>
  );
}
