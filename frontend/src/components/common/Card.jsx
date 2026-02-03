/**
 * Card container component
 */

export function Card({
  children,
  title,
  className = '',
  padding = true,
}) {
  return (
    <div
      className={`
        bg-bg-850 rounded-lg border border-bg-700 shadow-sm
        ${padding ? 'p-4' : ''}
        ${className}
      `}
    >
      {title && (
        <h3 className="font-semibold text-text-100 mb-3">{title}</h3>
      )}
      {children}
    </div>
  );
}

export default Card;
