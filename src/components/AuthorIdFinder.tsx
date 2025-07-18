import React, { useState } from 'react';
import { Search, User, ExternalLink, Loader2, CheckCircle, AlertCircle, Users } from 'lucide-react';
import { analytics } from '../services/analytics';

interface AuthorIdFinderProps {
  onAuthorIdFound?: (authorId: string, authorName: string) => void;
}

export const AuthorIdFinder: React.FC<AuthorIdFinderProps> = ({ onAuthorIdFound }) => {
  const [orcid, setOrcid] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    type: 'success' | 'error';
    message: string;
    authorId?: string;
    authorName?: string;
  } | null>(null);

  const DEFAULT_API_KEY = '7f59af901d2d86f78a1fd60c1bf9426a';

  const validateOrcid = (orcidInput: string): string => {
    const cleaned = orcidInput.trim().replace(/\s+/g, '');
    
    // Check if it's already in the correct format
    if (/^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/.test(cleaned)) {
      return cleaned;
    }
    
    // Remove any existing hyphens and check if it's 16 characters
    const digitsOnly = cleaned.replace(/-/g, '');
    if (digitsOnly.length === 16 && /^\d{15}[\dX]$/.test(digitsOnly)) {
      // Format with hyphens
      return `${digitsOnly.slice(0, 4)}-${digitsOnly.slice(4, 8)}-${digitsOnly.slice(8, 12)}-${digitsOnly.slice(12, 16)}`;
    }
    
    throw new Error('Please enter a valid ORCID (16-digit identifier)');
  };

  const findAuthorId = async () => {
    if (!orcid.trim()) {
      setResult({
        type: 'error',
        message: 'Please enter an ORCID'
      });
      return;
    }

    setLoading(true);
    setResult(null);

    try {
      // Validate and format ORCID
      const cleanOrcid = validateOrcid(orcid);
      
      // Track lookup attempt
      analytics.trackFeatureUsage('author_id_finder', 'orcid_lookup_started', { orcid: cleanOrcid });
      
      // Make API request
      const response = await fetch(
        `https://api.elsevier.com/analytics/scival/author/orcid/${cleanOrcid}?apiKey=${DEFAULT_API_KEY}`,
        {
          method: 'GET',
          headers: {
            'Accept': 'application/json',
            'User-Agent': 'SciVal-Research-Dashboard/1.0'
          }
        }
      );

      if (!response.ok) {
        let errorMessage = `API request failed with status ${response.status}`;
        
        if (response.status === 404) {
          errorMessage = 'No researcher found with this ORCID in SciVal database';
        } else if (response.status === 401) {
          errorMessage = 'API authentication failed. Please check the API key configuration.';
        } else if (response.status === 403) {
          errorMessage = 'API access denied. Your API key may not have the required permissions.';
        }
        
        // Track failed lookup
        analytics.trackAuthorIdLookup('orcid', false);
        analytics.trackError('orcid_lookup_error', errorMessage, { 
          orcid: cleanOrcid, 
          statusCode: response.status 
        });
        
        throw new Error(errorMessage);
      }

      const data = await response.json();

      // Extract researcher information
      if (data.author && data.author.id) {
        const authorId = data.author.id.toString();
        const authorName = data.author.name || 'Unknown';
        
        setResult({
          type: 'success',
          message: `Researcher found successfully! Scopus Author ID has been added to the search field above.`,
          authorId,
          authorName
        });

        // Track successful lookup
        analytics.trackAuthorIdLookup('orcid', true);
        analytics.trackFeatureUsage('author_id_finder', 'orcid_lookup_success', {
          orcid: cleanOrcid,
          authorId,
          authorName
        });

        // Notify parent component if callback provided
        if (onAuthorIdFound) {
          onAuthorIdFound(authorId, authorName);
        }
      } else {
        const errorMessage = 'Researcher ID not found in API response';
        analytics.trackAuthorIdLookup('orcid', false);
        analytics.trackError('orcid_lookup_error', errorMessage, { orcid: cleanOrcid });
        throw new Error(errorMessage);
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unexpected error occurred';
      setResult({
        type: 'error',
        message: errorMessage
      });
      
      // Track error if not already tracked
      if (!(error instanceof Error && error.message.includes('API request failed'))) {
        analytics.trackAuthorIdLookup('orcid', false);
        analytics.trackError('orcid_lookup_error', errorMessage, { orcid });
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !loading) {
      findAuthorId();
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      analytics.trackFeatureUsage('author_id_finder', 'copy_author_id', { authorId: text });
    });
  };

  const handleScholarProfilesClick = () => {
    analytics.trackAuthorIdLookup('scholar_profiles', true);
    analytics.trackFeatureUsage('author_id_finder', 'scholar_profiles_clicked');
  };

  return (
    <div className="bg-gradient-to-r from-green-50 to-emerald-50 rounded-xl p-6 border border-green-200">
      <div className="flex items-center mb-4">
        <User className="h-5 w-5 text-green-600 mr-2" />
        <h3 className="text-md font-semibold text-green-900">Find Scopus Author ID</h3>
      </div>
      
      <div className="space-y-4">
        {/* Scholar Profiles Option */}
        <div className="bg-blue-50 rounded-lg p-4 border border-blue-200">
          <div className="flex items-center mb-3">
            <Users className="h-5 w-5 text-blue-600 mr-2" />
            <h4 className="text-sm font-semibold text-blue-900">Option 1: Scholar Profiles</h4>
          </div>
          <p className="text-sm text-blue-800 mb-3">
            Browse HKUST researcher profiles to find Scopus Author IDs directly.
          </p>
          <a
            href="https://repository.hkust.edu.hk/ir/AuthorProfile/List/1"
            target="_blank"
            rel="noopener noreferrer"
            onClick={handleScholarProfilesClick}
            className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors duration-200 text-sm"
          >
            <Users className="h-4 w-4 mr-2" />
            Browse Scholar Profiles
            <ExternalLink className="h-4 w-4 ml-2" />
          </a>
        </div>

        {/* ORCID Lookup Option */}
        <div className="bg-green-50 rounded-lg p-4 border border-green-200">
          <div className="flex items-center mb-3">
            <Search className="h-5 w-5 text-green-600 mr-2" />
            <h4 className="text-sm font-semibold text-green-900">Option 2: Find by ORCID</h4>
          </div>
          
          <div>
            <label htmlFor="orcidInput" className="block text-sm font-medium text-green-800 mb-2">
              ORCID Identifier
            </label>
            <div className="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  id="orcidInput"
                  value={orcid}
                  onChange={(e) => setOrcid(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="ORCID Format: XXXX-XXXX-XXXX-XXXX (16-digit identifier)"
                  className="w-full pl-4 pr-4 py-3 border border-green-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all duration-200 bg-white text-slate-900 placeholder-slate-500"
                  disabled={loading}
                />
              </div>
              <button
                onClick={findAuthorId}
                disabled={loading || !orcid.trim()}
                className="px-4 py-3 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg font-medium hover:from-green-700 hover:to-emerald-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-md hover:shadow-lg flex items-center justify-center space-x-2"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                <span>{loading ? 'Searching...' : 'Find ID'}</span>
              </button>
            </div>
            <p className="text-xs text-green-700 mt-2">
              ORCID Format: XXXX-XXXX-XXXX-XXXX (16-digit identifier)
            </p>
          </div>

          {/* Result Display */}
          {result && (
            <div className={`rounded-lg p-4 border-l-4 mt-4 ${
              result.type === 'success' 
                ? 'bg-green-100 border-green-400' 
                : 'bg-red-100 border-red-400'
            }`}>
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  {result.type === 'success' ? (
                    <CheckCircle className="h-5 w-5 text-green-400" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-red-400" />
                  )}
                </div>
                <div className="ml-3 flex-1">
                  <h4 className={`text-sm font-medium ${
                    result.type === 'success' ? 'text-green-800' : 'text-red-800'
                  }`}>
                    {result.type === 'success' ? 'Success!' : 'Error'}
                  </h4>
                  <div className={`mt-2 text-sm ${
                    result.type === 'success' ? 'text-green-700' : 'text-red-700'
                  }`}>
                    <p>{result.message}</p>
                    
                    {result.type === 'success' && result.authorId && result.authorName && (
                      <div className="mt-3 space-y-2">
                        <div className="bg-white rounded-md p-3 border border-green-200">
                          <div className="grid grid-cols-1 gap-2">
                            <div>
                              <span className="font-medium text-green-900">Name:</span>
                              <span className="ml-2 text-green-800">{result.authorName}</span>
                            </div>
                            <div>
                              <span className="font-medium text-green-900">ORCID:</span>
                              <span className="ml-2 text-green-800">{orcid}</span>
                            </div>
                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-2 sm:space-y-0">
                              <div>
                                <span className="font-medium text-green-900">Scopus Author ID:</span>
                                <span className="ml-2 text-green-800 font-mono font-bold">{result.authorId}</span>
                                <span className="ml-2 text-xs text-green-600">(Added to search field)</span>
                              </div>
                              <button
                                onClick={() => copyToClipboard(result.authorId!)}
                                className="px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors duration-200 self-start sm:self-center"
                                title="Copy Scopus Author ID"
                              >
                                Copy Scopus ID
                              </button>
                            </div>
                          </div>
                        </div>
                        <p className="text-xs text-green-600">
                          💡 The Scopus Author ID has been automatically added to the search field above. You can also copy it manually if needed.
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Info Section */}
        <div className="bg-gray-100 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-900 mb-2">About Finding Scopus Author IDs:</h4>
          <ul className="text-xs text-gray-800 space-y-1">
            <li>• <strong>Scholar Profiles:</strong> Browse HKUST researcher profiles with pre-linked Scopus IDs</li>
            <li>• <strong>ORCID Lookup:</strong> Enter an ORCID to find the corresponding Scopus Author ID</li>
            <li>• ORCID is a persistent digital identifier for researchers</li>
            <li>• 
              <a 
                href="https://orcid.org/" 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center text-gray-700 hover:text-gray-900 underline"
                onClick={() => analytics.trackFeatureUsage('external_link', 'orcid_org')}
              >
                Learn more about ORCID
                <ExternalLink className="h-3 w-3 ml-1" />
              </a>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};