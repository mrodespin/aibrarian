/**
 * Mantiene la variable CSS --app-height sincronizada con la altura real
 * visible del viewport en iOS Safari.
 *
 * Por qué existe: `100dvh` se ajusta cuando aparece/desaparece la barra de
 * herramientas de Safari, pero NO se ajusta cuando aparece el teclado
 * virtual. El "layout viewport" (del que depende `dvh`) conserva su altura
 * completa mientras que el "visual viewport" (lo que el usuario realmente
 * ve) se encoge bajo el teclado. Al no coincidir ambos, Safari hace scroll
 * de todo el documento para mantener visible el input enfocado, lo que
 * produce el salto/desplazamiento del layout al empezar a escribir.
 *
 * `window.visualViewport` sí refleja la altura visible real (teclado
 * incluido), así que la usamos para fijar `--app-height` y que el layout
 * (clase `.h-app` en index.css) encoja exactamente al espacio disponible
 * en vez de quedar tapado por el teclado o forzar scroll del documento.
 *
 * Equivalente conceptual en JS/TS "vanilla": es lo mismo que un
 * `window.addEventListener('resize', ...)`, pero escuchando el
 * `VisualViewport` en lugar de `window`, que en Safari es la única fuente
 * fiable de la altura realmente visible.
 */
import { useEffect } from 'react';

export function useViewportHeight() {
  useEffect(() => {
    const viewport = window.visualViewport;

    const setAppHeight = () => {
      const height = viewport ? viewport.height : window.innerHeight;
      document.documentElement.style.setProperty('--app-height', `${height}px`);
    };

    setAppHeight();

    // Sin soporte de visualViewport (navegadores antiguos) nos quedamos
    // con el fallback CSS (100dvh) definido en index.css.
    if (!viewport) return undefined;

    viewport.addEventListener('resize', setAppHeight);
    viewport.addEventListener('scroll', setAppHeight);

    return () => {
      viewport.removeEventListener('resize', setAppHeight);
      viewport.removeEventListener('scroll', setAppHeight);
    };
  }, []);
}

export default useViewportHeight;
