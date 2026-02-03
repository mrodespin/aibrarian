/**
 * Alert/notification component
 */

export function Alert({
  children,
  type = 'info',
  onClose,
  className = '',
}) {
  const types = {
    info: 'bg-blue-50 text-blue-800 border-blue-200',
    success: 'bg-green-50 text-green-800 border-green-200',
    warning: 'bg-yellow-50 text-yellow-800 border-yellow-200',
    error: 'bg-red-50 text-red-800 border-red-200',
  };

  const icons = {
    info: '💡',
    success: '✓',
    warning: '⚠',
    error: '✕',
  };

  return (
    <div
      className={`
        flex items-start gap-3 p-4 rounded-lg border
        ${types[type]}
        ${className}
      `}
      role="alert"
    >
      <span className="flex-shrink-0">{icons[type]}</span>
      <div className="flex-1 text-sm">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="flex-shrink-0 hover:opacity-70"
          aria-label="Cerrar"
        >
          ✕
        </button>
      )}
    </div>
  );
}

export default Alert;
