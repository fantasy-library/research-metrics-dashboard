import React, { useState, useRef } from 'react';
import { BarChart3, FileText, TrendingUp, Info, Key, Eye, EyeOff, User, BookOpen, ExternalLink, Calendar, Filter, FileType } from 'lucide-react';
import { apiService, AuthorMetrics, APIError } from './services/api';
import MetricsTable from './components/MetricsTable';
import LoadingSpinner from './components/LoadingSpinner';
import { ErrorMessage } from './components/ErrorMessage';
import { DataSourceInfo } from './components/DataSourceInfo';
import { ExportButtons } from './components/ExportButtons';
import { AuthorIdFinder } from './components/AuthorIdFinder';
import { AdminAnalytics } from './components/AdminAnalytics';
import { ExportData } from './utils/exportUtils';
import { analytics } from './services/analytics';

interface AuthorResult {
  id: string;
  data: AuthorMetrics;
  isEntitlementError?: boolean;
  isRateLimitError?: boolean;
  selectedMetrics?: string[];
  metricOrder?: string[];
}

interface MetricOption {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
}

interface YearRangeOption {
  value: string;
  label: string;
  description: string;
}

interface IncludedDocsOption {
  value: string;
  label: string;
  description: string;
}

function App() {
  const [authorIds, setAuthorIds] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [showApiKeySection, setShowApiKeySection] = useState(false);
  const [showAuthorIdFinder, setShowAuthorIdFinder] = useState(false);
  const [results, setResults] = useState<AuthorResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [isEntitlementError, setIsEntitlementError] = useState(false);
  const [isRateLimitError, setIsRateLimitError] = useState(false);

  // Ref for the Analyze Metrics button
  const analyzeButtonRef = useRef<HTMLButtonElement>(null);

  // Function to scroll to Analyze Metrics button
  const scrollToAnalyzeButton = () => {
    analyzeButtonRef.current?.scrollIntoView({ 
      behavior: 'smooth', 
      block: 'center' 
    });
  };

  // Metrics selection state
  const [availableMetrics, setAvailableMetrics] = useState<MetricOption[]>([
    {
      id: 'publication',
      label: 'Publication',
      description: 'Scholarly output count by year',
      enabled: true
    },
    {
      id: 'fwci',
      label: 'Field-Weighted Citation Impact (FWCI)',
      description: 'Citation impact normalized by field',
      enabled: true
    },
    {
      id: 'topJournal',
      label: 'Top 10% Journal Percentile',
      description: 'Publications in top-tier journals',
      enabled: true
    },
    {
      id: 'citationCount',
      label: 'Citation Count',
      description: 'Total citation count',
      enabled: true
    },
    {
      id: 'hIndex',
      label: 'H-Index',
      description: 'Author productivity and citation impact',
      enabled: true
    },
    {
      id: 'citationsPerPublication',
      label: 'Citations Per Publication',
      description: 'Average citations per publication',
      enabled: true
    },
    {
      id: 'collaboration',
      label: 'Collaboration',
      description: 'Collaboration patterns by type (institutional, international, national, single authorship)',
      enabled: false
    },
    {
      id: 'academicCorporateCollaboration',
      label: 'Academic Corporate Collaboration',
      description: 'Academic-corporate collaboration patterns and breakdown',
      enabled: false
    }
  ]);

  // Year range selection state
  const [yearRangeOptions] = useState<YearRangeOption[]>([
    {
      value: '3yrs',
      label: 'Last 3 years',
      description: '3 complete years'
    },
    {
      value: '3yrsAndCurrent',
      label: 'Last 3 years + current',
      description: '3 complete years plus current year'
    },
    {
      value: '5yrs',
      label: 'Last 5 years (default)',
      description: '5 complete years'
    },
    {
      value: '5yrsAndCurrent',
      label: 'Last 5 years + current',
      description: '5 complete years plus current year'
    },
    {
      value: '10yrs',
      label: 'Last 10 years',
      description: '10 complete years'
    }
  ]);

  const [selectedYearRange, setSelectedYearRange] = useState('5yrs');

  // Document types selection state
  const [includedDocsOptions] = useState<IncludedDocsOption[]>([
    {
      value: 'AllPublicationTypes',
      label: 'All Publication Types (default)',
      description: 'Include all types of publications'
    },
    {
      value: 'ArticlesOnly',
      label: 'Articles Only',
      description: 'Include only journal articles'
    },
    {
      value: 'ArticlesReviews',
      label: 'Articles & Reviews',
      description: 'Include articles and review papers'
    },
    {
      value: 'ArticlesReviewsConferencePapers',
      label: 'Articles, Reviews & Conference Papers',
      description: 'Include articles, reviews, and conference papers'
    },
    {
      value: 'ArticlesConferencePapers',
      label: 'Articles & Conference Papers',
      description: 'Include articles and conference papers'
    },
    {
      value: 'BooksAndBookChapters',
      label: 'Books & Book Chapters',
      description: 'Include books and book chapters only'
    }
  ]);

  const [selectedIncludedDocs, setSelectedIncludedDocs] = useState('AllPublicationTypes');

  // Self-citations filter state
  const [includeSelfCitations, setIncludeSelfCitations] = useState(true);
  
  // Disclaimer state
  const [disclaimerDismissed, setDisclaimerDismissed] = useState(false);

  const handleSingleAuthor = async (authorId: string) => {
    try {
      const data = await apiService.getAuthorMetrics(authorId, apiKey, selectedYearRange, availableMetrics, selectedIncludedDocs, includeSelfCitations);
      return { id: authorId, data, isEntitlementError: false, isRateLimitError: false };
    } catch (err) {
      const isEntitlement = err instanceof APIError && err.isEntitlementError;
      const isRateLimit = err instanceof APIError && err.isRateLimitError;
      
      // Track error
      analytics.trackError(
        isEntitlement ? 'api_entitlement_error' : isRateLimit ? 'api_rate_limit_error' : 'api_error',
        err instanceof Error ? err.message : 'Unknown error',
        { authorId, hasCustomApiKey: !!apiKey, yearRange: selectedYearRange, includedDocs: selectedIncludedDocs }
      );
      
      return { 
        id: authorId, 
        data: { 
          error: err instanceof Error ? err.message : 'Unknown error',
          metrics: {
            hIndex: { value: 'N/A', dataSource: { name: 'N/A', url: '' } },
            scholarlyOutput: { byYear: {}, total: 'N/A' },
            fwci: { byYear: {}, total: 'N/A' },
            topJournal: { byYear: {}, total: 'N/A' },
            citationCount: { byYear: {}, total: 'N/A' },
            citationsPerPublication: { byYear: {}, total: 'N/A' },
            collaboration: { byYear: {}, total: 'N/A' },
            academicCorporateCollaboration: { byYear: {}, total: 'N/A' }
          }
        },
        isEntitlementError: isEntitlement,
        isRateLimitError: isRateLimit
      };
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authorIds.trim()) return;

    setLoading(true);
    setError('');
    setIsEntitlementError(false);
    setIsRateLimitError(false);
    setResults([]);

    try {
      const ids = authorIds.split(',').map(id => id.trim()).filter(id => id);
      
      // Track search analytics
      analytics.trackSearch(ids, !!apiKey, selectedYearRange, availableMetrics.filter(m => m.enabled).map(m => m.id));
      
      if (ids.length === 1) {
        const result = await handleSingleAuthor(ids[0]);
        setResults([result]);
        if (result.isEntitlementError) {
          setIsEntitlementError(true);
        }
        if (result.isRateLimitError) {
          setIsRateLimitError(true);
        }
      } else {
        try {
          const data = await apiService.processMultipleAuthors(ids, apiKey, selectedYearRange, availableMetrics, selectedIncludedDocs, includeSelfCitations);
          const processedResults = data.map(item => ({
            id: item.id,
            data: item.data,
            isEntitlementError: false,
            isRateLimitError: false
          }));
          setResults(processedResults);
        } catch (err) {
          if (err instanceof APIError && (err.isEntitlementError || err.isRateLimitError)) {
            setError(err.message);
            setIsEntitlementError(err.isEntitlementError);
            setIsRateLimitError(err.isRateLimitError);
            
            // Track error
            analytics.trackError(
              err.isEntitlementError ? 'multiple_authors_entitlement_error' : 'multiple_authors_rate_limit_error',
              err.message,
              {
                authorCount: ids.length,
                hasCustomApiKey: !!apiKey,
                yearRange: selectedYearRange,
                includedDocs: selectedIncludedDocs
              }
            );
          } else {
            // Fallback to individual processing
            const results = await Promise.all(ids.map(handleSingleAuthor));
            setResults(results);
            
            // Check if any result has errors
            const hasEntitlementError = results.some(r => r.isEntitlementError);
            const hasRateLimitError = results.some(r => r.isRateLimitError);
            if (hasEntitlementError) {
              setIsEntitlementError(true);
            }
            if (hasRateLimitError) {
              setIsRateLimitError(true);
            }
          }
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unexpected error occurred';
      const isEntitlement = err instanceof APIError && err.isEntitlementError;
      const isRateLimit = err instanceof APIError && err.isRateLimitError;
      setError(errorMessage);
      setIsEntitlementError(isEntitlement);
      setIsRateLimitError(isRateLimit);
      
      // Track general error
      analytics.trackError('search_error', errorMessage, {
        isEntitlementError: isEntitlement,
        isRateLimitError: isRateLimit,
        hasCustomApiKey: !!apiKey,
        yearRange: selectedYearRange,
        includedDocs: selectedIncludedDocs
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectionChange = (authorId: string, selectedMetrics: string[], metricOrder: string[]) => {
    setResults(prev => prev.map(result => 
      result.id === authorId 
        ? { ...result, selectedMetrics, metricOrder }
        : result
    ));

    // Track metrics selection
    analytics.trackFeatureUsage('metrics_table', 'selection_changed', {
      authorId,
      selectedMetricsCount: selectedMetrics.length,
      totalMetrics: availableMetrics.length
    });
  };

  const handleAuthorIdFound = (authorId: string, authorName: string) => {
    // Add the found author ID to the search field
    const currentIds = authorIds.trim();
    if (currentIds) {
      setAuthorIds(`${currentIds}, ${authorId}`);
    } else {
      setAuthorIds(authorId);
    }

    // Track successful author ID lookup
    analytics.trackAuthorIdLookup('orcid', true);
  };

  const handleExportClick = (format: 'pdf' | 'excel') => {
    const validResults = results.filter(result => !result.data.error);
    const selectedMetrics = validResults[0]?.selectedMetrics || [];
    
    // Track export analytics
    analytics.trackExport(format, validResults.length, selectedMetrics);
  };

  const handleMetricToggle = (metricId: string) => {
    setAvailableMetrics(prev => 
      prev.map(metric => 
        metric.id === metricId 
          ? { ...metric, enabled: !metric.enabled }
          : metric
      )
    );

    // Track metric toggle
    analytics.trackFeatureUsage('metrics_selection', 'metric_toggled', {
      metricId,
      enabled: !availableMetrics.find(m => m.id === metricId)?.enabled
    });
  };

  const handleYearRangeChange = (value: string) => {
    setSelectedYearRange(value);
    
    // Track year range change
    analytics.trackFeatureUsage('year_range_selection', 'range_changed', {
      yearRange: value
    });
  };

  const handleIncludedDocsChange = (value: string) => {
    setSelectedIncludedDocs(value);
    
    // Track document type change
    analytics.trackFeatureUsage('document_type_selection', 'type_changed', {
      includedDocs: value
    });
  };

  const handleIncludeSelfCitationsChange = (value: boolean) => {
    setIncludeSelfCitations(value);
    
    // Track self-citations filter change
    analytics.trackFeatureUsage('self_citations_filter', 'filter_changed', {
      includeSelfCitations: value
    });
  };

  const hasValidResults = results.some(result => !result.data.error);
  const dataSource = results.find(result => result.data.dataSource)?.data.dataSource;

  // Prepare export data with selection and ordering
  const exportData: ExportData[] = results
    .filter(result => !result.data.error)
    .map(result => ({
      authorId: result.id,
      authorName: result.data.authorName,
      metrics: result.data.metrics,
      dataSource: result.data.dataSource,
      selectedMetrics: result.selectedMetrics,
      metricOrder: result.metricOrder
    }));

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50 flex flex-col">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-sm border-b border-slate-200/60 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between space-y-4 lg:space-y-0">
            {/* Logo Section */}
            <div className="flex flex-col sm:flex-row sm:items-center space-y-3 sm:space-y-0 sm:space-x-4">
              {/* HKUST Logos */}
              <div className="flex items-center justify-center sm:justify-start space-x-3">
                <a 
                  href="https://hkust.edu.hk/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:opacity-80 transition-opacity duration-200"
                  onClick={() => analytics.trackFeatureUsage('external_link', 'hkust_main')}
                >
                  <img 
                    src="https://library.hkust.edu.hk/wp-content/themes/hkustlib/hkust_alignment/profiles/ust/modules/custom/hkust_signature_affiliate/assets/images/HKUST-logo.png"
                    alt="HKUST Logo"
                    className="h-10 sm:h-12 w-auto"
                  />
                </a>
                <div className="w-px bg-slate-300 h-10 sm:h-12 mx-2"></div>
                <a 
                  href="https://library.hkust.edu.hk/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:opacity-80 transition-opacity duration-200"
                  onClick={() => analytics.trackFeatureUsage('external_link', 'hkust_library')}
                >
                  <img 
                    src="https://library.hkust.edu.hk/wp-content/themes/hkustlib/hkust_alignment/core/assets/library/library_logo.png_transparent_bkgd_h300.png"
                    alt="HKUST Library Logo"
                    className="h-10 sm:h-12 w-auto"
                  />
                </a>
              </div>
              
              {/* Title Section */}
              <div className="flex items-center space-x-3 justify-center sm:justify-start">
                <div className="p-2 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl">
                  <BarChart3 className="h-5 w-5 sm:h-6 sm:w-6 text-white" />
                </div>
                <div className="text-center sm:text-left">
                  <div className="flex items-center justify-center sm:justify-start gap-3">
                    <h1 className="text-xl sm:text-2xl font-bold bg-gradient-to-r from-slate-800 to-slate-600 bg-clip-text text-transparent">
                      Research Impact Dashboard
                    </h1>
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold bg-gradient-to-r from-orange-500 to-red-500 text-white shadow-sm">
                      BETA
                    </span>
                  </div>
                  <p className="text-xs sm:text-sm text-slate-600">Analyze author metrics and research impact</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        {/* Disclaimer in Header */}
        {!disclaimerDismissed && (
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-t border-amber-200/50">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
              <div className="flex flex-col space-y-4">
                {/* Main disclaimer content */}
                <div className="flex items-start space-x-4">
                  <Info className="h-5 w-5 text-amber-600 flex-shrink-0 mt-1" />
                  <div className="flex-1">
                    <p className="text-sm text-amber-800 text-justify leading-relaxed">
                      <span className="font-semibold">Disclaimer:</span> This research metrics dashboard has been generated using data provided by Elsevier's SciVal APIs. Please be aware that metrics presented in this dashboard are subject to change over time as the underlying data is updated and refined. Contact us if you need a more customized report, see this sample report as reference.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      setDisclaimerDismissed(true);
                      analytics.trackFeatureUsage('disclaimer', 'dismissed');
                    }}
                    className="px-3 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 transition-colors duration-200 flex items-center space-x-2 flex-shrink-0"
                  >
                    <span className="text-lg">×</span>
                    <span>Acknowledge & Close</span>
                  </button>
                </div>
                
                {/* External links */}
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-end space-y-2 sm:space-y-0 sm:space-x-6 pl-9">
                  <div className="flex items-center space-x-2">
                    <ExternalLink className="h-4 w-4 text-amber-600" />
                    <a 
                      href="https://dev.elsevier.com/scival.html#/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-amber-700 font-medium underline hover:text-amber-900 transition-colors duration-200"
                      onClick={() => analytics.trackFeatureUsage('external_link', 'scival_api_docs')}
                    >
                      Learning more about SciVal APIs
                    </a>
                  </div>
                  <div className="flex items-center space-x-2">
                    <BookOpen className="h-4 w-4 text-amber-600" />
                    <a 
                      href="https://libguides.hkust.edu.hk/research-impact/author-impact"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-amber-700 font-medium underline hover:text-amber-900 transition-colors duration-200 whitespace-nowrap"
                      onClick={() => analytics.trackFeatureUsage('external_link', 'research_metrics_guide')}
                    >
                      Understanding Research Metrics
                    </a>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Search Form */}
        <div className="bg-white/70 backdrop-blur-sm rounded-2xl shadow-xl border border-white/20 p-6 sm:p-8 mb-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Search Configuration Section */}
            <div className="bg-gradient-to-r from-slate-50 to-blue-50 rounded-xl p-6 border border-slate-200">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-4 sm:space-y-0">
                <h2 className="text-lg font-semibold text-slate-800">Search Configuration</h2>
                <div className="flex flex-col sm:flex-row space-y-2 sm:space-y-0 sm:space-x-3">
                  <button
                    type="button"
                    onClick={() => {
                      setShowAuthorIdFinder(!showAuthorIdFinder);
                      analytics.trackFeatureUsage('author_id_finder', showAuthorIdFinder ? 'closed' : 'opened');
                    }}
                    className="flex items-center justify-center space-x-2 px-3 py-2 bg-gradient-to-r from-green-100 to-emerald-200 hover:from-green-200 hover:to-emerald-300 text-green-700 rounded-lg text-sm font-medium transition-all duration-200 shadow-sm hover:shadow-md"
                  >
                    <User className="h-4 w-4" />
                    <span>{showAuthorIdFinder ? 'Hide' : 'Find'} Scopus ID</span>
                  </button>
                  {/*
                  <button
                    type="button"
                    onClick={() => {
                      setShowApiKeySection(!showApiKeySection);
                      analytics.trackFeatureUsage('api_settings', showApiKeySection ? 'closed' : 'opened');
                    }}
                    className="flex items-center justify-center space-x-2 px-3 py-2 bg-gradient-to-r from-slate-100 to-slate-200 hover:from-slate-200 hover:to-slate-300 text-slate-700 rounded-lg text-sm font-medium transition-all duration-200 shadow-sm hover:shadow-md"
                  >
                    <Settings className="h-4 w-4" />
                    <span>{showApiKeySection ? 'Hide' : 'Show'} API Settings</span>
                  </button>
                  */}
                </div>
              </div>

              {/* Author ID Finder - Collapsible */}
              {showAuthorIdFinder && (
                <AuthorIdFinder onAuthorIdFound={handleAuthorIdFound} />
              )}

              {/* API Key Input - Collapsible */}
              {showApiKeySection && (
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-6 border border-blue-200 mt-4">
                  <div className="flex items-center mb-4">
                    <Key className="h-5 w-5 text-blue-600 mr-2" />
                    <h3 className="text-md font-semibold text-blue-900">Custom API Key Configuration</h3>
                  </div>
                  
                  <div className="space-y-4">
                    <div>
                      <label htmlFor="apiKey" className="block text-sm font-medium text-blue-800 mb-2">
                        SciVal API Key (Optional)
                      </label>
                      <div className="relative">
                        <input
                          type={showApiKey ? "text" : "password"}
                          id="apiKey"
                          value={apiKey}
                          onChange={(e) => setApiKey(e.target.value)}
                          placeholder={apiKey ? "••••••••••••••••••••••••••••••••" : "Enter your SciVal API key"}
                          className="w-full pl-4 pr-16 py-3 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 bg-white text-slate-900 placeholder-slate-500"
                          disabled={loading}
                        />
                        <button
                          type="button"
                          onClick={() => setShowApiKey(!showApiKey)}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 transition-colors duration-200"
                          disabled={loading}
                        >
                          {showApiKey ? (
                            <EyeOff className="h-4 w-4" />
                          ) : (
                            <Eye className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </div>
                    
                    <div className="bg-blue-100 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-blue-900 mb-2">About API Keys & Rate Limits:</h4>
                      <ul className="text-xs text-blue-800 space-y-1">
                        <li>• If no API key is provided, the system will use the default configuration</li>
                        <li>• Your custom API key is never stored and only used for the current session</li>
                        <li>• Custom API keys allow you to use your own SciVal API quota and avoid rate limits</li>
                        <li>• <strong>Rate Limit Tips:</strong> Wait between searches, process authors individually</li>
                        <li>• 
                          <a 
                            href="https://dev.elsevier.com/"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center text-blue-700 hover:text-blue-900 underline"
                            onClick={() => analytics.trackFeatureUsage('external_link', 'elsevier_dev_portal')}
                          >
                            Get your API key from the Elsevier Developer Portal
                            <ExternalLink className="h-3 w-3 ml-1" />
                          </a>
                        </li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* Author IDs Input */}
              <div className="max-w-full mt-4">
                <label htmlFor="authorIds" className="block text-sm font-semibold text-slate-700 mb-3">
                  Scopus Author ID
                </label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 transform -translate-y-1/2 h-6 w-6 text-slate-500 z-10" />
                  <input
                    type="text"
                    id="authorIds"
                    value={authorIds}
                    onChange={(e) => setAuthorIds(e.target.value)}
                    placeholder="Enter your Scopus Author ID. Don't know your Scopus ID? → Find Scopus ID"
                    className="w-full pl-12 pr-4 py-4 border border-slate-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 bg-white text-slate-900 placeholder-slate-500"
                    disabled={loading}
                    required
                  />
                </div>
                <p className="mt-2 text-xs text-slate-500">
                  Select the metrics below and press Analyze Metrics
                  <button
                    type="button"
                    onClick={scrollToAnalyzeButton}
                    className="ml-2 inline-flex items-center px-2 py-1 bg-blue-100 text-blue-700 rounded-md text-xs font-medium hover:bg-blue-200 transition-colors duration-200"
                    title="Scroll to Analyze Metrics"
                  >
                    <TrendingUp className="h-3 w-3 mr-1" />
                    Go to Analyze
                  </button>
                </p>
              </div>
            </div>

            {/* Year Range, Document Types, and Self-Citations Selection */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Year Range Selection */}
              <div className="bg-gradient-to-r from-blue-50 to-cyan-50 rounded-xl p-6 border border-blue-200">
                <div className="flex items-center mb-4">
                  <Calendar className="h-5 w-5 text-blue-600 mr-2" />
                  <h3 className="text-md font-semibold text-blue-900">Filter by Year Range</h3>
                </div>
                
                <div className="space-y-3">
                  <label htmlFor="yearRange" className="block text-sm font-medium text-blue-800">
                    Select time period for analysis
                  </label>
                  <select
                    id="yearRange"
                    value={selectedYearRange}
                    onChange={(e) => handleYearRangeChange(e.target.value)}
                    className="w-full px-4 py-3 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 bg-white text-slate-900"
                    disabled={loading}
                  >
                    {yearRangeOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-blue-700">
                    {yearRangeOptions.find(opt => opt.value === selectedYearRange)?.description}
                  </p>
                </div>
              </div>

              {/* Document Types Selection */}
              <div className="bg-gradient-to-r from-emerald-50 to-green-50 rounded-xl p-6 border border-emerald-200">
                <div className="flex items-center mb-4">
                  <FileType className="h-5 w-5 text-emerald-600 mr-2" />
                  <h3 className="text-md font-semibold text-emerald-900">Filter by Document Types</h3>
                </div>
                
                <div className="space-y-3">
                  <label htmlFor="includedDocs" className="block text-sm font-medium text-emerald-800">
                    Select publication types to include in analysis
                  </label>
                  <select
                    id="includedDocs"
                    value={selectedIncludedDocs}
                    onChange={(e) => handleIncludedDocsChange(e.target.value)}
                    className="w-full px-4 py-3 border border-emerald-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all duration-200 bg-white text-slate-900"
                    disabled={loading}
                  >
                    {includedDocsOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-emerald-700">
                    {includedDocsOptions.find(opt => opt.value === selectedIncludedDocs)?.description}
                  </p>
                </div>
              </div>

              {/* Self-Citations Selection */}
              <div className="bg-gradient-to-r from-orange-50 to-amber-50 rounded-xl p-6 border border-orange-200">
                <div className="flex items-center mb-4">
                  <Filter className="h-5 w-5 text-orange-600 mr-2" />
                  <h3 className="text-md font-semibold text-orange-900">Self-Citations Filter</h3>
                </div>
                
                <div className="space-y-3">
                  <label className="block text-sm font-medium text-orange-800">
                    Include self-citations in calculations
                  </label>
                  <div className="space-y-3">
                    <label className="flex items-center">
                      <input
                        type="radio"
                        name="includeSelfCitations"
                        value="true"
                        checked={includeSelfCitations === true}
                        onChange={() => handleIncludeSelfCitationsChange(true)}
                        className="h-4 w-4 text-orange-600 focus:ring-orange-500 border-orange-300"
                        disabled={loading}
                      />
                      <span className="ml-2 text-sm text-orange-800">Include</span>
                    </label>
                    <label className="flex items-center">
                      <input
                        type="radio"
                        name="includeSelfCitations"
                        value="false"
                        checked={includeSelfCitations === false}
                        onChange={() => handleIncludeSelfCitationsChange(false)}
                        className="h-4 w-4 text-orange-600 focus:ring-orange-500 border-orange-300"
                        disabled={loading}
                      />
                      <span className="ml-2 text-sm text-orange-800">Exclude</span>
                    </label>
                  </div>
                  <p className="text-xs text-orange-700">
                    Self-citations are citations where an author cites their own previous work. Including them may increase citation counts and H-index values.
                  </p>
                </div>
              </div>
            </div>

            {/* Metrics Selection Section */}
            <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-xl p-6 border border-purple-200">
              <div className="flex items-center mb-4">
                <Filter className="h-5 w-5 text-purple-600 mr-2" />
                <h3 className="text-md font-semibold text-purple-900">Select Metrics to Include</h3>
              </div>
              
              {/* Core Metrics */}
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-purple-800 mb-3">Core Research Metrics</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {availableMetrics.slice(0, 6).map((metric) => (
                    <div key={metric.id} className="bg-white rounded-lg p-4 border border-purple-200 hover:border-purple-300 transition-colors duration-200">
                      <div className="flex items-start space-x-3">
                        <div className="flex-shrink-0 mt-1">
                          <button
                            type="button"
                            onClick={() => handleMetricToggle(metric.id)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 ${
                              metric.enabled ? 'bg-purple-600' : 'bg-gray-300'
                            }`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${
                                metric.enabled ? 'translate-x-6' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className={`text-sm font-medium transition-colors duration-200 ${
                            metric.enabled ? 'text-purple-900' : 'text-gray-500'
                          }`}>
                            {metric.label}
                          </h4>
                          <p className={`text-xs mt-1 transition-colors duration-200 ${
                            metric.enabled ? 'text-purple-700' : 'text-gray-400'
                          }`}>
                            {metric.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Collaboration Metrics */}
              <div>
                <h4 className="text-sm font-semibold text-purple-800 mb-3">Collaboration Metrics</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {availableMetrics.slice(6).map((metric) => (
                    <div key={metric.id} className="bg-white rounded-lg p-4 border border-purple-200 hover:border-purple-300 transition-colors duration-200">
                      <div className="flex items-start space-x-3">
                        <div className="flex-shrink-0 mt-1">
                          <button
                            type="button"
                            onClick={() => handleMetricToggle(metric.id)}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 ${
                              metric.enabled ? 'bg-purple-600' : 'bg-gray-300'
                            }`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${
                                metric.enabled ? 'translate-x-6' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className={`text-sm font-medium transition-colors duration-200 ${
                            metric.enabled ? 'text-purple-900' : 'text-gray-500'
                          }`}>
                            {metric.label}
                          </h4>
                          <p className={`text-xs mt-1 transition-colors duration-200 ${
                            metric.enabled ? 'text-purple-700' : 'text-gray-400'
                          }`}>
                            {metric.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="mt-4 flex items-center justify-between">
                <p className="text-sm text-purple-700">
                  {availableMetrics.filter(m => m.enabled).length} of {availableMetrics.length} metrics selected
                </p>
                <div className="flex space-x-2">
                  <button
                    type="button"
                    onClick={() => setAvailableMetrics(prev => prev.map(m => ({ ...m, enabled: true })))}
                    className="px-3 py-1 text-xs bg-purple-600 text-white rounded-md hover:bg-purple-700 transition-colors duration-200"
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={() => setAvailableMetrics(prev => prev.map(m => ({ ...m, enabled: false })))}
                    className="px-3 py-1 text-xs bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors duration-200"
                  >
                    Clear All
                  </button>
                </div>
              </div>
            </div>
            
            <button
              ref={analyzeButtonRef}
              type="submit"
              disabled={loading || !authorIds.trim() || availableMetrics.filter(m => m.enabled).length === 0}
              className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white py-4 px-6 rounded-xl font-semibold hover:from-blue-700 hover:to-indigo-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 shadow-lg hover:shadow-xl"
            >
              {loading ? (
                <div className="flex items-center justify-center space-x-2">
                  <LoadingSpinner size="sm" />
                  <span>Analyzing...</span>
                </div>
              ) : (
                <div className="flex items-center justify-center space-x-2">
                  <TrendingUp className="h-5 w-5" />
                  <span>Analyze Metrics</span>
                </div>
              )}
            </button>

            {/* Validation Message */}
            {availableMetrics.filter(m => m.enabled).length === 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-sm text-red-800">
                  Please select at least one metric to analyze.
                </p>
              </div>
            )}
          </form>
        </div>

        {/* Error Display */}
        {error && (
          <div className="mb-8">
            <ErrorMessage 
              message={error} 
              isEntitlementError={isEntitlementError}
              isRateLimitError={isRateLimitError}
            />
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div className="space-y-8">
            {/* Data Source Info */}
            {hasValidResults && dataSource && (
              <DataSourceInfo dataSource={dataSource} />
            )}

            {/* Metrics Tables */}
            {results.map((result, index) => (
              <div key={result.id} className="bg-white/70 backdrop-blur-sm rounded-2xl shadow-xl border border-white/20 overflow-hidden">
                <div className="bg-gradient-to-r from-slate-50 to-blue-50 px-4 sm:px-6 py-4 border-b border-slate-200/60">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-2 sm:space-y-0">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-gradient-to-br from-slate-500 to-slate-600 rounded-lg">
                        <User className="h-4 w-4 text-white" />
                      </div>
                      <div>
                        <h2 className="text-base sm:text-lg font-semibold text-slate-800">
                          {result.data.authorName ? (
                            <>
                              {result.data.authorName}
                              <span className="text-sm font-normal text-slate-600 ml-2 block sm:inline">
                                (ID: {result.id})
                              </span>
                            </>
                          ) : (
                            `Author ID: ${result.id}`
                          )}
                        </h2>
                        <p className="text-sm text-slate-600">Research metrics and impact analysis</p>
                      </div>
                    </div>
                    {results.length > 1 && (
                      <span className="px-3 py-1 bg-blue-100 text-blue-800 text-sm font-medium rounded-full self-start sm:self-center">
                        {index + 1} of {results.length}
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="p-4 sm:p-6">
                  {result.data.error ? (
                    <ErrorMessage 
                      message={result.data.error} 
                      isEntitlementError={result.isEntitlementError}
                      isRateLimitError={result.isRateLimitError}
                    />
                  ) : (
                    <MetricsTable 
                      metrics={result.data.metrics} 
                      dataSource={result.data.dataSource}
                      availableMetrics={availableMetrics}
                      onSelectionChange={(selectedMetrics, metricOrder) => 
                        handleSelectionChange(result.id, selectedMetrics, metricOrder)
                      }
                    />
                  )}
                </div>
              </div>
            ))}

            {/* Export Buttons - Moved below metrics */}
            {hasValidResults && (
              <div className="bg-white/70 backdrop-blur-sm rounded-2xl shadow-xl border border-white/20 p-6">
                <div className="flex items-center mb-4">
                  <div className="p-2 bg-gradient-to-br from-green-500 to-green-600 rounded-lg mr-3">
                    <FileText className="h-4 w-4 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-slate-800">Export Results</h3>
                </div>
                <p className="text-sm text-slate-600 mb-4">
                  Download your research metrics data in PDF or Excel format. Only selected metrics will be included in the export, in the order you've arranged them.
                </p>
                <ExportButtons data={exportData} onExport={handleExportClick} />
              </div>
            )}
          </div>
        )}
      </main>

      {/* Admin Analytics Component - Hidden by default */}
      <AdminAnalytics />

      {/* Footer */}
      <footer className="bg-slate-800 text-white mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Resources Section */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Resources</h3>
              <ul className="space-y-2">
                <li>
                  <a 
                    href="https://library.hkust.edu.hk" 
                    className="text-slate-300 hover:text-white transition-colors duration-200"
                    onClick={() => analytics.trackFeatureUsage('external_link', 'hkust_library')}
                  >
                    HKUST Library
                  </a>
                </li>
              </ul>
            </div>

            {/* Contact & Support Section */}
            <div>
              <h3 className="text-lg font-semibold mb-4">Contact & Support</h3>
              <div className="space-y-2 text-slate-300">
                <p>
                  <a 
                    href="mailto:library@ust.hk" 
                    className="hover:text-white transition-colors duration-200"
                    onClick={() => analytics.trackFeatureUsage('contact', 'email')}
                  >
                    library@ust.hk
                  </a>
                </p>
                <p>
                  <a 
                    href="tel:+85223586772" 
                    className="hover:text-white transition-colors duration-200"
                    onClick={() => analytics.trackFeatureUsage('contact', 'phone')}
                  >
                    +852 2358 6772
                  </a>
                </p>
              </div>
            </div>

            {/* Address Section */}
            <div>
              <h3 className="text-lg font-semibold mb-4">HKUST Library</h3>
              <div className="text-slate-300 space-y-1">
                <p>Hong Kong University of Science and Technology</p>
                <p>Clear Water Bay, Kowloon, Hong Kong</p>
              </div>
            </div>
          </div>

          {/* Bottom Section */}
          <div className="border-t border-slate-700 mt-8 pt-8">
            <div className="flex justify-center items-center">
              <p className="text-sm text-slate-300 text-center">
                © 2025 Hong Kong University of Science and Technology Library. All rights reserved.
              </p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;