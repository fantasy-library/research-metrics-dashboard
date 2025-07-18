import React from 'react';
import { AlertCircle, Key, ExternalLink, Clock, RefreshCw } from 'lucide-react';

interface ErrorMessageProps {
  message: string;
  isEntitlementError?: boolean;
  isRateLimitError?: boolean;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({ 
  message, 
  isEntitlementError = false,
  isRateLimitError = false 
}) => {
  const getErrorConfig = () => {
    if (isRateLimitError) {
      return {
        bgColor: 'bg-orange-50',
        borderColor: 'border-orange-400',
        textColor: 'text-orange-800',
        headerColor: 'text-orange-800',
        bodyColor: 'text-orange-700',
        icon: <Clock className="h-5 w-5 text-orange-400" />,
        title: 'Rate Limit Exceeded'
      };
    } else if (isEntitlementError) {
      return {
        bgColor: 'bg-amber-50',
        borderColor: 'border-amber-400',
        textColor: 'text-amber-800',
        headerColor: 'text-amber-800',
        bodyColor: 'text-amber-700',
        icon: <Key className="h-5 w-5 text-amber-400" />,
        title: 'API Access Issue'
      };
    } else {
      return {
        bgColor: 'bg-red-50',
        borderColor: 'border-red-400',
        textColor: 'text-red-800',
        headerColor: 'text-red-800',
        bodyColor: 'text-red-700',
        icon: <AlertCircle className="h-5 w-5 text-red-400" />,
        title: 'Error'
      };
    }
  };

  const config = getErrorConfig();

  return (
    <div className={`rounded-lg p-6 border-l-4 ${config.bgColor} ${config.borderColor} ${config.textColor}`}>
      <div className="flex items-start">
        <div className="flex-shrink-0">
          {config.icon}
        </div>
        <div className="ml-3 flex-1">
          <h3 className={`text-sm font-medium ${config.headerColor}`}>
            {config.title}
          </h3>
          <div className={`mt-2 text-sm ${config.bodyColor}`}>
            <p className="whitespace-pre-wrap">{message}</p>
            
            {isRateLimitError && (
              <div className="mt-4 space-y-2">
                <div className="flex items-center space-x-2">
                  <RefreshCw className="h-4 w-4" />
                  <p className="font-medium">The system is automatically retrying your request</p>
                </div>
                <p className="font-medium">To avoid rate limits in the future:</p>
                <ul className="list-disc list-inside space-y-1 ml-2">
                  <li>Wait a few seconds between searches when processing multiple authors</li>
                  <li>Consider using your own SciVal API key for higher rate limits</li>
                  <li>Process authors one at a time instead of in batches</li>
                  <li>Contact your institution about upgrading your API quota</li>
                </ul>
                <div className="mt-3 pt-3 border-t border-orange-200">
                  <a
                    href="https://dev.elsevier.com/api_key_settings.html"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-sm text-orange-700 hover:text-orange-900 underline"
                  >
                    <ExternalLink className="h-4 w-4 mr-1" />
                    Manage Your API Key Settings
                  </a>
                </div>
              </div>
            )}

            {isEntitlementError && (
              <div className="mt-4 space-y-2">
                <p className="font-medium">To resolve this issue:</p>
                <ul className="list-disc list-inside space-y-1 ml-2">
                  <li>Verify your SciVal API key is active and valid</li>
                  <li>Ensure your API key has the required entitlements for author metrics</li>
                  <li>Contact your institution's SciVal administrator</li>
                  <li>Check with Elsevier support if needed</li>
                </ul>
                <div className="mt-3 pt-3 border-t border-amber-200">
                  <a
                    href="https://dev.elsevier.com/documentation/SciValAPI.wadl"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center text-sm text-amber-700 hover:text-amber-900 underline"
                  >
                    <ExternalLink className="h-4 w-4 mr-1" />
                    SciVal API Documentation
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};