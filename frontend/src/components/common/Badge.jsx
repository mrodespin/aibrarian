/**
 * Status badge component
 */

export function Badge({
  children,
  variant = 'default',
  className = '',
}) {
  const variants = {
    default: 'bg-bg-800 text-text-200 border border-bg-700',
    success: 'bg-success-500/20 text-success-400 border border-success-500/30',
    error: 'bg-error-500/20 text-error-400 border border-error-500/30',
    warning: 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30',
    info: 'bg-accent-500/20 text-accent-400 border border-accent-500/30',
  };

  return (
    <span
      className={`
        inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium
        ${variants[variant]}
        ${className}
      `}
    >
      {children}
    </span>
  );
}

export default Badge;
