export type NavItem = {
  href: string;
  activePatterns?: RegExp[];
};

export function findActiveNavHref(pathname: string, items: NavItem[]): string | null {
  const normalizedPathname = pathname.replace(/\/$/, "") || "/";

  const matches = items
    .flatMap((item) => {
      const href = item.href.replace(/\/$/, "") || "/";
      const matchedByHref = (() => {
      if (normalizedPathname === href) return true;
      if (href === "/") return false;
      return normalizedPathname.startsWith(`${href}/`);
      })();
      const matchedByPattern = item.activePatterns?.some((pattern) => pattern.test(normalizedPathname));

      return matchedByHref || matchedByPattern ? [href] : [];
    })
    .sort((a, b) => b.length - a.length);

  return matches[0] ?? null;
}
