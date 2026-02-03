/**
 * Reusable input component
 */

export function Input({
  label,
  error,
  className = '',
  ...props
}) {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-text-100 mb-1">
          {label}
        </label>
      )}
      <input
        className={`
          w-full px-3 py-2 border rounded-lg
          bg-bg-850 text-text-50 placeholder-text-400
          focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500
          disabled:bg-bg-900 disabled:cursor-not-allowed disabled:text-text-400
          transition-all
          ${error ? 'border-error-500' : 'border-bg-700 hover:border-bg-600'}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-error-400">{error}</p>
      )}
    </div>
  );
}

export default Input;
