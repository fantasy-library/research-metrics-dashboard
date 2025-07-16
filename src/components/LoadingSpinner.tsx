import React from 'react';
import { Loader2 } from 'lucide-react';

interface LoadingSpinnerProps {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = 'Loading...', size = 'md' }) => {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-6 w-6',
    lg: 'h-8 w-8'
  };

  if (size === 'sm') {
    return <Loader2 className={`animate-spin ${sizeClasses[size]} text-current`} />;
  }

  return (
    <div className="flex items-center justify-center p-8 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
      <div className="flex items-center space-x-3">
        <Loader2 className={`animate-spin ${sizeClasses[size]} text-blue-600`} />
        <span className="text-blue-800 font-medium">{message}</span>
      </div>
    </div>
  );
};

export default LoadingSpinner;