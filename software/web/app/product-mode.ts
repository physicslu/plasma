export type ProductMode = "production" | "engineering";

export const PRODUCT_MODE_ROUTES: Record<ProductMode, string> = {
  production: "/fleet",
  engineering: "/engineering",
};

export function productModeForPath(pathname: string): ProductMode | null {
  if (pathname === "/fleet" || pathname.startsWith("/fleet/")) return "production";
  if (pathname === "/engineering" || pathname.startsWith("/engineering/")) return "engineering";
  return null;
}
