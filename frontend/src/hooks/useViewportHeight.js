/**
 * Keeps --app-height and --app-offset-top in sync with the window
 * that's actually visible on iOS Safari, as a fallback for when
 * `interactive-widget=resizes-content` (see index.html) isn't supported.
 *
 * Why this exists: `100dvh` adjusts when Safari's toolbar shows/hides,
 * but it does NOT adjust when the virtual keyboard appears. The
 * "layout viewport" (what `dvh` depends on, and the document's
 * coordinate system) keeps its full height and position, while the
 * "visual viewport" (what the user actually sees) shrinks AND shifts
 * (`offsetTop`) under the keyboard, because Safari tries to keep the
 * focused input visible without doing a real scroll of the document
 * (which we already block via `overflow: hidden` on html/body).
 *
 * If we only fixed the height (as this hook's previous version did)
 * without also fixing the offset, the app's container stays anchored
 * at the document's y=0 coordinate while the visible window looks at a
 * shifted slice of that same page: the result is that the input
 * appears to "float" mid-screen with an empty gap below it, which is
 * exactly the bug seen in production.
 *
 * The fix (the same pattern web.dev documents for VisualViewport):
 * anchor the container with `position: fixed` (the `.h-app` class in
 * index.css, outside the document's normal flow) and translate it
 * vertically by `visualViewport.offsetTop`, in addition to setting its
 * height to `visualViewport.height`.
 *
 * Conceptual "vanilla" JS/TS equivalent: it's the same as a
 * `window.addEventListener('resize', ...)`, but listening on
 * `VisualViewport` instead of `window`, which on Safari is the only
 * reliable source for which part of the page is actually in view.
 */
import { useEffect } from 'react';

export function useViewportHeight() {
  useEffect(() => {
    const viewport = window.visualViewport;
    const root = document.documentElement;

    const setViewportVars = () => {
      const height = viewport ? viewport.height : window.innerHeight;
      const offsetTop = viewport ? viewport.offsetTop : 0;
      root.style.setProperty('--app-height', `${height}px`);
      root.style.setProperty('--app-offset-top', `${offsetTop}px`);
    };

    setViewportVars();

    // Without visualViewport support (older browsers) we fall back to
    // the CSS fallback (100dvh, no offset) defined in index.css.
    if (!viewport) return undefined;

    viewport.addEventListener('resize', setViewportVars);
    viewport.addEventListener('scroll', setViewportVars);

    return () => {
      viewport.removeEventListener('resize', setViewportVars);
      viewport.removeEventListener('scroll', setViewportVars);
    };
  }, []);
}

export default useViewportHeight;
