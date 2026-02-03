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
    info: 'bg-accent-500/10 text-accent-400 border-accent-500/30',
    success: 'bg-success-500/10 text-success-400 border-success-500/30',
    warning: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30',
    error: 'bg-error-500/10 text-error-400 border-error-500/30',
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
