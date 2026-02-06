# ADR-005: React + Vite + Tailwind para el frontend

**Estado:** Aceptada
**Fecha:** Diciembre 2025

---

## Contexto

El TFM necesita una interfaz de usuario para dos funcionalidades principales:
- **Chat conversacional**: Interfaz para hacer preguntas al sistema RAG
- **Panel de sincronización**: Gestión de ingesta de documentos (PDFs y Notion)

La interfaz debe ser moderna, responsive y demostrar competencia en desarrollo frontend.

## Alternativas evaluadas

### 1. Server-Side Rendering (Next.js / Remix)
- SEO optimizado, routing server-side
- Mayor complejidad de deploy (necesita servidor Node.js)
- Innecesario para una aplicación privada sin requisitos SEO

### 2. Vue.js + Nuxt
- Framework progresivo, curva de aprendizaje suave
- Ecosistema más pequeño que React
- Menos demandado en el mercado laboral

### 3. React SPA + Vite
- Ecosistema más grande y maduro
- Vite ofrece HMR instantáneo y builds rápidos
- SPA es suficiente para una aplicación de uso interno
- Conocimiento directamente aplicable al mercado laboral

## Decisión

**React 19 + Vite 7 + Tailwind CSS v4** por:

1. **React 19**: Última versión estable con mejoras en rendering y hooks
2. **Vite 7**: Build tool moderno, startup instantáneo vs webpack (Create React App ya deprecated)
3. **Tailwind CSS v4**: Utilidad-first CSS con dark mode nativo, configuración via `@theme` en CSS (sin tailwind.config.js)
4. **SPA**: No hay requisitos de SEO ni SSR. La app es privada y local

### Stack frontend completo

| Librería | Versión | Propósito |
|----------|---------|-----------|
| React | 19.x | UI framework |
| Vite | 7.x | Build tool + dev server |
| Tailwind CSS | 4.x | Estilos utility-first |
| React Router | 7.x | Routing SPA |
| Axios | - | HTTP client para la API |

## Consecuencias

**Positivas:**
- Hot Module Replacement instantáneo durante desarrollo
- Dark mode implementado con Tailwind sin librerías adicionales
- Bundle final optimizado (<500KB gzipped)
- Despliegue simple: archivos estáticos servidos por `npm run dev`

**Negativas:**
- Requiere Node.js 18+ en la máquina del evaluador
- SPA tiene carga inicial mayor que SSR (irrelevante para uso local)
- Tailwind v4 es relativamente nuevo, menos documentación legacy disponible
