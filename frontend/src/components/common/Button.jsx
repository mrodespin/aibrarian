/**
 * Reusable button component
 */

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  className = '',
  ...props
}) {
  const baseStyles = 'inline-flex items-center justify-center font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-bg-900 disabled:opacity-50 disabled:cursor-not-allowed';

  const variants = {
    primary: 'bg-gradient-to-r from-accent-500 to-violet-600 text-white hover:from-accent-600 hover:to-violet-700 focus:ring-accent-500 shadow-lg shadow-accent-500/30',
    secondary: 'bg-bg-800 text-text-100 hover:bg-bg-700 focus:ring-bg-700 border border-bg-700',
    danger: 'bg-error-500 text-white hover:bg-error-600 focus:ring-error-500',
    ghost: 'bg-transparent text-text-200 hover:bg-bg-800 hover:text-text-50 focus:ring-bg-700',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-sm',
    lg: 'px-6 py-3 text-base',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  );
}

export default Button;
