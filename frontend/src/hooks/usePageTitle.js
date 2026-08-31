import { useEffect } from "react";
import { siteName, siteTitle } from "../constants/site";

/**
 * 022: per-route tab titles. Client-side only on purpose — scrapers never
 * run this; it exists for humans' tabs and for Google, which does. Pages
 * pass their name ("Courses", a course title); no argument restores the
 * site-wide default, which is also what every page restores on unmount so
 * a title never outlives its page.
 */
export default function usePageTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} — ${siteName}` : siteTitle;
    return () => {
      document.title = siteTitle;
    };
  }, [title]);
}
