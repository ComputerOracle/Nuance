export function SiteFooter() {
  return (
    <footer className="border-t border-border-3 px-8 py-7">
      <div className="mx-auto flex max-w-[1160px] flex-wrap items-center justify-between gap-4 text-[13px] text-fg-faint-2">
        <div>Nuance · built on GenLayer</div>
        <div className="flex gap-6">
          <a href="#how" className="hover:text-fg-hover">
            How it works
          </a>
          <a href="#use-cases" className="hover:text-fg-hover">
            Use cases
          </a>
        </div>
      </div>
    </footer>
  );
}
