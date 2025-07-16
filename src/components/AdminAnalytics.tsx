import React, { useState, useEffect } from 'react';
import { BarChart3, Download, Search, AlertCircle, Clock, Eye, Shield, Key, Globe, Monitor, Smartphone, Tablet, Users, TrendingUp, MapPin, ExternalLink } from 'lucide-react';
import { analytics } from '../services/analytics';

export const AdminAnalytics: React.FC = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [adminKey, setAdminKey] = useState('');
  const [activeTab, setActiveTab] = useState<'overview' | 'traffic' | 'behavior' | 'technical'>('overview');
  const [summary, setSummary] = useState({
    totalEvents: 0,
    searches: 0,
    exports: 0,
    errors: 0,
    sessionDuration: 0,
    pageViews: 0,
    bounceRate: 0,
    topReferrers: [] as Array<{ referrer: string; count: number }>,
    topCountries: [] as Array<{ country: string; count: number }>,
    deviceBreakdown: { desktop: 0, mobile: 0, tablet: 0 },
    browserBreakdown: {} as Record<string, number>,
    utmSources: [] as Array<{ source: string; count: number }>
  });
  const [recentEvents, setRecentEvents] = useState<any[]>([]);

  const ADMIN_ACCESS_KEY = 'hkust-lib-admin-2025';

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const urlAdminKey = urlParams.get('admin');
    const storedAdminKey = localStorage.getItem('admin_access');
    
    if (urlAdminKey === ADMIN_ACCESS_KEY || storedAdminKey === ADMIN_ACCESS_KEY) {
      setIsAuthenticated(true);
      setIsVisible(true);
      if (urlAdminKey) {
        localStorage.setItem('admin_access', ADMIN_ACCESS_KEY);
        window.history.replaceState({}, document.title, window.location.pathname);
      }
    }

    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'A') {
        e.preventDefault();
        setIsVisible(true);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  useEffect(() => {
    if (isVisible && isAuthenticated) {
      const summaryData = analytics.getAdvancedAnalyticsSummary();
      setSummary(summaryData);

      const events = JSON.parse(localStorage.getItem('analytics_events') || '[]');
      setRecentEvents(events.slice(-20).reverse());
    }
  }, [isVisible, isAuthenticated]);

  const handleAdminLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (adminKey === ADMIN_ACCESS_KEY) {
      setIsAuthenticated(true);
      localStorage.setItem('admin_access', ADMIN_ACCESS_KEY);
      analytics.trackFeatureUsage('admin_analytics', 'authenticated');
    } else {
      alert('Invalid admin access key');
      analytics.trackError('admin_auth_failed', 'Invalid admin key provided');
    }
  };

  const handleExportData = () => {
    const data = analytics.exportAnalyticsData();
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `research-dashboard-analytics-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    analytics.trackFeatureUsage('admin_analytics', 'export_data');
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
    setIsVisible(false);
    localStorage.removeItem('admin_access');
    setAdminKey('');
  };

  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const formatTimestamp = (timestamp: string): string => {
    return new Date(timestamp).toLocaleString();
  };

  const getDeviceIcon = (deviceType: string) => {
    switch (deviceType) {
      case 'mobile': return <Smartphone className="h-4 w-4" />;
      case 'tablet': return <Tablet className="h-4 w-4" />;
      default: return <Monitor className="h-4 w-4" />;
    }
  };

  if (!isVisible) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-7xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-red-600 to-red-700 text-white p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Shield className="h-6 w-6" />
              <h2 className="text-xl font-bold">Advanced Analytics Dashboard</h2>
              <span className="px-2 py-1 bg-red-800 text-xs rounded-full">ADMIN ONLY</span>
            </div>
            <div className="flex items-center space-x-3">
              {isAuthenticated && (
                <button
                  onClick={handleLogout}
                  className="text-red-200 hover:text-white transition-colors duration-200 text-sm"
                >
                  Logout
                </button>
              )}
              <button
                onClick={() => setIsVisible(false)}
                className="text-white hover:text-red-200 transition-colors duration-200"
              >
                <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
          {!isAuthenticated ? (
            /* Admin Login Form */
            <div className="max-w-md mx-auto">
              <div className="text-center mb-6">
                <Key className="h-12 w-12 text-red-600 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900">Admin Access Required</h3>
                <p className="text-sm text-gray-600 mt-2">
                  Enter the admin access key to view comprehensive analytics
                </p>
              </div>
              
              <form onSubmit={handleAdminLogin} className="space-y-4">
                <div>
                  <label htmlFor="adminKey" className="block text-sm font-medium text-gray-700 mb-2">
                    Admin Access Key
                  </label>
                  <input
                    type="password"
                    id="adminKey"
                    value={adminKey}
                    onChange={(e) => setAdminKey(e.target.value)}
                    placeholder="Enter admin access key"
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
                    required
                  />
                </div>
                
                <button
                  type="submit"
                  className="w-full bg-red-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-red-700 transition-colors duration-200"
                >
                  Access Analytics
                </button>
              </form>
            </div>
          ) : (
            /* Analytics Dashboard Content */
            <>
              {/* Tab Navigation */}
              <div className="flex space-x-1 mb-6 bg-gray-100 rounded-lg p-1">
                {[
                  { id: 'overview', label: 'Overview', icon: BarChart3 },
                  { id: 'traffic', label: 'Traffic Sources', icon: Globe },
                  { id: 'behavior', label: 'User Behavior', icon: Users },
                  { id: 'technical', label: 'Technical', icon: Monitor }
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id as any)}
                    className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors duration-200 ${
                      activeTab === tab.id
                        ? 'bg-white text-red-600 shadow-sm'
                        : 'text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    <tab.icon className="h-4 w-4" />
                    <span>{tab.label}</span>
                  </button>
                ))}
              </div>

              {/* Overview Tab */}
              {activeTab === 'overview' && (
                <>
                  {/* Summary Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                    <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-lg p-4 border border-blue-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-blue-600">Total Events</p>
                          <p className="text-2xl font-bold text-blue-900">{summary.totalEvents}</p>
                        </div>
                        <Eye className="h-8 w-8 text-blue-500" />
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-lg p-4 border border-green-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-green-600">Searches</p>
                          <p className="text-2xl font-bold text-green-900">{summary.searches}</p>
                        </div>
                        <Search className="h-8 w-8 text-green-500" />
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-lg p-4 border border-purple-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-purple-600">Page Views</p>
                          <p className="text-2xl font-bold text-purple-900">{summary.pageViews}</p>
                        </div>
                        <TrendingUp className="h-8 w-8 text-purple-500" />
                      </div>
                    </div>

                    <div className="bg-gradient-to-br from-orange-50 to-orange-100 rounded-lg p-4 border border-orange-200">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-orange-600">Bounce Rate</p>
                          <p className="text-2xl font-bold text-orange-900">{summary.bounceRate}%</p>
                        </div>
                        <Clock className="h-8 w-8 text-orange-500" />
                      </div>
                    </div>
                  </div>

                  {/* Error Summary */}
                  {summary.errors > 0 && (
                    <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
                      <div className="flex items-center space-x-2">
                        <AlertCircle className="h-5 w-5 text-red-500" />
                        <span className="text-sm font-medium text-red-800">
                          {summary.errors} error{summary.errors !== 1 ? 's' : ''} detected
                        </span>
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Traffic Sources Tab */}
              {activeTab === 'traffic' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Top Referrers */}
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <ExternalLink className="h-5 w-5 mr-2" />
                      Top Referrers
                    </h3>
                    <div className="space-y-3">
                      {summary.topReferrers.length === 0 ? (
                        <p className="text-gray-500">No referrer data available</p>
                      ) : (
                        summary.topReferrers.map((referrer, index) => (
                          <div key={index} className="flex items-center justify-between bg-white rounded-lg p-3">
                            <span className="text-sm font-medium text-gray-900">{referrer.referrer}</span>
                            <span className="text-sm text-gray-600">{referrer.count} visits</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* UTM Sources */}
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <TrendingUp className="h-5 w-5 mr-2" />
                      Campaign Sources
                    </h3>
                    <div className="space-y-3">
                      {summary.utmSources.length === 0 ? (
                        <p className="text-gray-500">No campaign data available</p>
                      ) : (
                        summary.utmSources.map((source, index) => (
                          <div key={index} className="flex items-center justify-between bg-white rounded-lg p-3">
                            <span className="text-sm font-medium text-gray-900">{source.source}</span>
                            <span className="text-sm text-gray-600">{source.count} visits</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Geographic Data */}
                  <div className="bg-gray-50 rounded-lg p-6 lg:col-span-2">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <MapPin className="h-5 w-5 mr-2" />
                      Geographic Distribution
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                      {summary.topCountries.length === 0 ? (
                        <p className="text-gray-500 col-span-full">No geographic data available</p>
                      ) : (
                        summary.topCountries.map((country, index) => (
                          <div key={index} className="flex items-center justify-between bg-white rounded-lg p-3">
                            <span className="text-sm font-medium text-gray-900">{country.country}</span>
                            <span className="text-sm text-gray-600">{country.count} users</span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* User Behavior Tab */}
              {activeTab === 'behavior' && (
                <div className="space-y-6">
                  {/* Recent Events */}
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent User Activity</h3>
                    <div className="space-y-3 max-h-96 overflow-y-auto">
                      {recentEvents.length === 0 ? (
                        <p className="text-gray-500 text-center py-4">No recent activity</p>
                      ) : (
                        recentEvents.map((event, index) => (
                          <div key={index} className="bg-white rounded-lg p-3 border border-gray-200">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-3">
                                <div className={`w-2 h-2 rounded-full ${
                                  event.category === 'error' ? 'bg-red-500' :
                                  event.category === 'research' ? 'bg-green-500' :
                                  event.category === 'engagement' ? 'bg-blue-500' :
                                  'bg-gray-500'
                                }`} />
                                <div>
                                  <p className="text-sm font-medium text-gray-900">
                                    {event.action.replace(/_/g, ' ').replace(/\b\w/g, (l: string) => l.toUpperCase())}
                                  </p>
                                  {event.label && (
                                    <p className="text-xs text-gray-600">{event.label}</p>
                                  )}
                                </div>
                              </div>
                              <span className="text-xs text-gray-500">
                                {formatTimestamp(event.timestamp)}
                              </span>
                            </div>
                            {event.metadata && Object.keys(event.metadata).length > 0 && (
                              <div className="mt-2 text-xs text-gray-600">
                                <details className="cursor-pointer">
                                  <summary className="hover:text-gray-800">View details</summary>
                                  <pre className="mt-1 bg-gray-100 p-2 rounded text-xs overflow-x-auto">
                                    {JSON.stringify(event.metadata, null, 2)}
                                  </pre>
                                </details>
                              </div>
                            )}
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Technical Tab */}
              {activeTab === 'technical' && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Device Breakdown */}
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                      <Monitor className="h-5 w-5 mr-2" />
                      Device Types
                    </h3>
                    <div className="space-y-3">
                      {Object.entries(summary.deviceBreakdown).map(([device, count]) => (
                        <div key={device} className="flex items-center justify-between bg-white rounded-lg p-3">
                          <div className="flex items-center space-x-2">
                            {getDeviceIcon(device)}
                            <span className="text-sm font-medium text-gray-900 capitalize">{device}</span>
                          </div>
                          <span className="text-sm text-gray-600">{count} users</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Browser Breakdown */}
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Browser Distribution</h3>
                    <div className="space-y-3">
                      {Object.entries(summary.browserBreakdown).length === 0 ? (
                        <p className="text-gray-500">No browser data available</p>
                      ) : (
                        Object.entries(summary.browserBreakdown)
                          .sort(([,a], [,b]) => b - a)
                          .map(([browser, count]) => (
                            <div key={browser} className="flex items-center justify-between bg-white rounded-lg p-3">
                              <span className="text-sm font-medium text-gray-900">{browser}</span>
                              <span className="text-sm text-gray-600">{count} users</span>
                            </div>
                          ))
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Export Button */}
              <div className="mt-8 flex justify-center">
                <button
                  onClick={handleExportData}
                  className="flex items-center space-x-2 px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors duration-200"
                >
                  <Download className="h-4 w-4" />
                  <span>Export Complete Analytics Data</span>
                </button>
              </div>

              {/* Admin Notice */}
              <div className="mt-6 bg-red-50 border border-red-200 rounded-lg p-4">
                <h4 className="text-sm font-medium text-red-900 mb-2">Advanced Analytics Features</h4>
                <ul className="text-xs text-red-800 space-y-1">
                  <li>• <strong>User Spread Tracking:</strong> Referrers, UTM campaigns, geographic distribution</li>
                  <li>• <strong>Behavioral Analytics:</strong> Scroll depth, time on page, interaction patterns</li>
                  <li>• <strong>Technical Insights:</strong> Device types, browsers, screen resolutions, connection speeds</li>
                  <li>• <strong>Performance Monitoring:</strong> Page load times, error tracking, API response times</li>
                  <li>• <strong>Privacy Compliant:</strong> No personal data collection, GDPR/CCPA friendly</li>
                </ul>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};