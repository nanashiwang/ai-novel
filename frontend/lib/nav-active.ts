export type NavItem = {
  href: string;
};

export function findActiveNavHref(pathname: string, items: NavItem[]): string | null {
  const normalizedPathname = pathname.replace(/\/$/, "") || "/";

  const matches = items
    .map((item) => item.href.replace(/\/$/, "") || "/")
    .filter((href) => {
      if (normalizedPathname === href) return true;
      if (href === "/") return false;
      return normalizedPathname.startsWith(`${href}/`);
    })
    .sort((a, b) => b.length - a.length);

  return matches[0] ?? null;
}
