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
        bg-white rounded-lg border border-gray-200 shadow-sm
        ${padding ? 'p-4' : ''}
        ${className}
      `}
    >
      {title && (
        <h3 className="font-semibold text-gray-900 mb-3">{title}</h3>
      )}
      {children}
    </div>
  );
}

export default Card;
