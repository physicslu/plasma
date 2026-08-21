import type { AnchorHTMLAttributes, MouseEvent } from "react";
import { navigate } from "./next-navigation";

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
};

export default function Link({ href, onClick, target, ...props }: LinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      (target && target !== "_self")
    ) {
      return;
    }

    const destination = new URL(href, window.location.href);
    if (destination.origin !== window.location.origin) return;
    event.preventDefault();
    navigate(`${destination.pathname}${destination.search}${destination.hash}`);
  }

  return <a {...props} href={href} target={target} onClick={handleClick} />;
}
