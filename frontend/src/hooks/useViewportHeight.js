/**
 * Mantiene --app-height y --app-offset-top sincronizadas con la ventana
 * realmente visible en iOS Safari, como fallback para cuando
 * `interactive-widget=resizes-content` (ver index.html) no está soportado.
 *
 * Por qué existe: `100dvh` se ajusta cuando aparece/desaparece la barra de
 * herramientas de Safari, pero NO se ajusta cuando aparece el teclado
 * virtual. El "layout viewport" (del que depende `dvh`, y el sistema de
 * coordenadas del documento) conserva su altura y posición completas,
 * mientras que el "visual viewport" (lo que el usuario realmente ve) se
 * encoge Y se desplaza (`offsetTop`) bajo el teclado, porque Safari intenta
 * mantener visible el input enfocado sin hacer un scroll real del
 * documento (que ya bloqueamos con `overflow: hidden` en html/body).
 *
 * Si solo corrigiéramos la altura (como hacía la versión anterior de este
 * hook) sin corregir también el offset, el contenedor de la app se queda
 * anclado en la coordenada y=0 del documento mientras la ventana visible
 * mira un trozo desplazado de esa misma página: el resultado es que el
 * input parece "flotar" a media pantalla con un hueco vacío debajo, que es
 * justo el bug que se veía en producción.
 *
 * La solución (el mismo patrón que documenta web.dev para VisualViewport):
 * anclar el contenedor con `position: fixed` (clase `.h-app` en index.css,
 * fuera del flujo normal del documento) y trasladarlo verticalmente por
 * `visualViewport.offsetTop`, además de fijar su altura a
 * `visualViewport.height`.
 *
 * Equivalente conceptual en JS/TS "vanilla": es lo mismo que un
 * `window.addEventListener('resize', ...)`, pero escuchando el
 * `VisualViewport` en lugar de `window`, que en Safari es la única fuente
 * fiable de qué parte de la página está realmente a la vista.
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

    // Sin soporte de visualViewport (navegadores antiguos) nos quedamos
    // con el fallback CSS (100dvh, sin offset) definido en index.css.
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
