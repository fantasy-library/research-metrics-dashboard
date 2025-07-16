// Advanced Analytics service with comprehensive tracking capabilities
export interface AnalyticsEvent {
  event: string;
  category: string;
  action: string;
  label?: string;
  value?: number;
  userId?: string;
  sessionId?: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface UserSession {
  sessionId: string;
  userId: string;
  startTime: string;
  endTime?: string;
  pageViews: number;
  events: number;
  referrer: string;
  utmSource?: string;
  utmMedium?: string;
  utmCampaign?: string;
  utmTerm?: string;
  utmContent?: string;
  userAgent: string;
  screenResolution: string;
  language: string;
  timezone: string;
  ipAddress?: string;
  country?: string;
  city?: string;
  device: {
    type: 'desktop' | 'mobile' | 'tablet';
    os: string;
    browser: string;
  };
}

class AdvancedAnalyticsService {
  private events: AnalyticsEvent[] = [];
  private sessionId: string;
  private userId: string;
  private session: UserSession;
  private pageLoadTime: number;
  private isFirstVisit: boolean;
  private backendAvailable: boolean = false; // Start as false to prevent initial failed requests

  constructor() {
    this.pageLoadTime = Date.now();
    this.sessionId = this.generateSessionId();
    this.userId = this.getUserId();
    this.isFirstVisit = this.checkFirstVisit();
    this.session = this.initializeSession();
    this.initializeTracking();
    this.setupAdvancedTracking();
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private getUserId(): string {
    let userId = localStorage.getItem('research_dashboard_user_id');
    if (!userId) {
      userId = `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      localStorage.setItem('research_dashboard_user_id', userId);
    }
    return userId;
  }

  private checkFirstVisit(): boolean {
    const hasVisited = localStorage.getItem('research_dashboard_visited');
    if (!hasVisited) {
      localStorage.setItem('research_dashboard_visited', 'true');
      return true;
    }
    return false;
  }

  private parseUTMParameters(): {
    utmSource?: string;
    utmMedium?: string;
    utmCampaign?: string;
    utmTerm?: string;
    utmContent?: string;
  } {
    const urlParams = new URLSearchParams(window.location.search);
    return {
      utmSource: urlParams.get('utm_source') || undefined,
      utmMedium: urlParams.get('utm_medium') || undefined,
      utmCampaign: urlParams.get('utm_campaign') || undefined,
      utmTerm: urlParams.get('utm_term') || undefined,
      utmContent: urlParams.get('utm_content') || undefined,
    };
  }

  private detectDevice(): UserSession['device'] {
    const userAgent = navigator.userAgent;
    
    // Detect device type
    let deviceType: 'desktop' | 'mobile' | 'tablet' = 'desktop';
    if (/tablet|ipad|playbook|silk/i.test(userAgent)) {
      deviceType = 'tablet';
    } else if (/mobile|iphone|ipod|android|blackberry|opera|mini|windows\sce|palm|smartphone|iemobile/i.test(userAgent)) {
      deviceType = 'mobile';
    }

    // Detect OS
    let os = 'Unknown';
    if (userAgent.includes('Windows')) os = 'Windows';
    else if (userAgent.includes('Mac')) os = 'macOS';
    else if (userAgent.includes('Linux')) os = 'Linux';
    else if (userAgent.includes('Android')) os = 'Android';
    else if (userAgent.includes('iOS')) os = 'iOS';

    // Detect browser
    let browser = 'Unknown';
    if (userAgent.includes('Chrome')) browser = 'Chrome';
    else if (userAgent.includes('Firefox')) browser = 'Firefox';
    else if (userAgent.includes('Safari')) browser = 'Safari';
    else if (userAgent.includes('Edge')) browser = 'Edge';
    else if (userAgent.includes('Opera')) browser = 'Opera';

    return { type: deviceType, os, browser };
  }

  private initializeSession(): UserSession {
    const utmParams = this.parseUTMParameters();
    const device = this.detectDevice();

    return {
      sessionId: this.sessionId,
      userId: this.userId,
      startTime: new Date().toISOString(),
      pageViews: 0,
      events: 0,
      referrer: document.referrer || 'direct',
      ...utmParams,
      userAgent: navigator.userAgent,
      screenResolution: `${screen.width}x${screen.height}`,
      language: navigator.language,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      device
    };
  }

  private async getLocationData(): Promise<{ country?: string; city?: string; ipAddress?: string }> {
    try {
      // Use a free IP geolocation service
      const response = await fetch('https://ipapi.co/json/');
      if (response.ok) {
        const data = await response.json();
        return {
          country: data.country_name,
          city: data.city,
          ipAddress: data.ip
        };
      }
    } catch (error) {
      console.warn('Failed to get location data:', error);
    }
    return {};
  }

  private initializeTracking(): void {
    // Track page load performance
    window.addEventListener('load', () => {
      const loadTime = Date.now() - this.pageLoadTime;
      this.track('page_load_complete', 'performance', 'page_load', undefined, loadTime, {
        load_time_ms: loadTime,
        is_first_visit: this.isFirstVisit
      });
    });

    // Track page visibility changes
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        this.track('page_hidden', 'engagement', 'visibility_change', 'hidden');
      } else {
        this.track('page_visible', 'engagement', 'visibility_change', 'visible');
      }
    });

    // Track scroll depth
    this.setupScrollTracking();

    // Track time on page
    this.setupTimeTracking();

    // Track session end
    window.addEventListener('beforeunload', () => {
      this.endSession();
    });

    // Track initial page view
    this.trackPageView();

    // Get location data asynchronously
    this.getLocationData().then(locationData => {
      this.session = { ...this.session, ...locationData };
    });

    // Periodic session updates
    setInterval(() => {
      this.updateSession();
      this.flush();
    }, 30000); // Every 30 seconds
  }

  private setupAdvancedTracking(): void {
    // Track clicks on external links
    document.addEventListener('click', (e) => {
      const target = e.target as HTMLElement;
      const link = target.closest('a');
      
      if (link && link.href) {
        const isExternal = !link.href.startsWith(window.location.origin);
        if (isExternal) {
          this.track('external_link_click', 'navigation', 'external_link', link.href, undefined, {
            link_text: link.textContent?.trim(),
            link_position: this.getElementPosition(link)
          });
        }
      }
    });

    // Track form interactions
    document.addEventListener('focus', (e) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
        this.track('form_field_focus', 'interaction', 'form_focus', target.id || target.name || 'unnamed');
      }
    }, true);

    // Track copy/paste events
    document.addEventListener('copy', () => {
      this.track('content_copied', 'interaction', 'copy');
    });

    document.addEventListener('paste', () => {
      this.track('content_pasted', 'interaction', 'paste');
    });

    // Track keyboard shortcuts
    document.addEventListener('keydown', (e) => {
      if (e.ctrlKey || e.metaKey) {
        const key = e.key.toLowerCase();
        if (['c', 'v', 'x', 'z', 'y', 'a', 's', 'f'].includes(key)) {
          this.track('keyboard_shortcut', 'interaction', 'shortcut', `${e.ctrlKey ? 'ctrl' : 'cmd'}+${key}`);
        }
      }
    });

    // Track window resize
    window.addEventListener('resize', () => {
      this.track('window_resize', 'interaction', 'resize', `${window.innerWidth}x${window.innerHeight}`);
    });

    // Track connection type (if available)
    if ('connection' in navigator) {
      const connection = (navigator as any).connection;
      this.track('connection_info', 'technical', 'connection', connection.effectiveType, undefined, {
        downlink: connection.downlink,
        rtt: connection.rtt,
        saveData: connection.saveData
      });
    }
  }

  private setupScrollTracking(): void {
    let maxScroll = 0;
    const scrollMilestones = [25, 50, 75, 90, 100];
    const trackedMilestones = new Set<number>();

    const trackScroll = () => {
      const scrollPercent = Math.round(
        (window.scrollY / (document.documentElement.scrollHeight - window.innerHeight)) * 100
      );
      
      maxScroll = Math.max(maxScroll, scrollPercent);

      scrollMilestones.forEach(milestone => {
        if (scrollPercent >= milestone && !trackedMilestones.has(milestone)) {
          trackedMilestones.add(milestone);
          this.track('scroll_depth', 'engagement', 'scroll', `${milestone}%`, milestone);
        }
      });
    };

    let scrollTimeout: NodeJS.Timeout;
    window.addEventListener('scroll', () => {
      clearTimeout(scrollTimeout);
      scrollTimeout = setTimeout(trackScroll, 100);
    });
  }

  private setupTimeTracking(): void {
    const timeIntervals = [30, 60, 120, 300, 600]; // 30s, 1m, 2m, 5m, 10m
    const trackedIntervals = new Set<number>();

    setInterval(() => {
      const timeOnPage = Math.floor((Date.now() - this.pageLoadTime) / 1000);
      
      timeIntervals.forEach(interval => {
        if (timeOnPage >= interval && !trackedIntervals.has(interval)) {
          trackedIntervals.add(interval);
          this.track('time_on_page', 'engagement', 'time_milestone', `${interval}s`, interval);
        }
      });
    }, 10000); // Check every 10 seconds
  }

  private getElementPosition(element: Element): string {
    const rect = element.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    
    if (rect.top < viewportHeight * 0.33) return 'top';
    if (rect.top < viewportHeight * 0.66) return 'middle';
    return 'bottom';
  }

  private trackPageView(): void {
    this.session.pageViews++;
    
    this.track('page_view', 'navigation', 'page_view', window.location.pathname, undefined, {
      page_title: document.title,
      page_url: window.location.href,
      referrer: document.referrer,
      utm_source: this.session.utmSource,
      utm_medium: this.session.utmMedium,
      utm_campaign: this.session.utmCampaign,
      is_first_visit: this.isFirstVisit,
      session_page_views: this.session.pageViews
    });
  }

  private updateSession(): void {
    this.session.events = this.events.length;
    
    // Save session data
    localStorage.setItem('current_session', JSON.stringify(this.session));
  }

  private endSession(): void {
    this.session.endTime = new Date().toISOString();
    const sessionDuration = new Date(this.session.endTime).getTime() - new Date(this.session.startTime).getTime();
    
    this.track('session_end', 'engagement', 'session_end', undefined, Math.floor(sessionDuration / 1000), {
      session_duration_ms: sessionDuration,
      total_events: this.session.events,
      total_page_views: this.session.pageViews
    });

    // Save completed session
    const completedSessions = JSON.parse(localStorage.getItem('completed_sessions') || '[]');
    completedSessions.push(this.session);
    
    // Keep only last 10 sessions to prevent storage bloat
    if (completedSessions.length > 10) {
      completedSessions.splice(0, completedSessions.length - 10);
    }
    
    localStorage.setItem('completed_sessions', JSON.stringify(completedSessions));
    
    this.flush();
  }

  track(
    event: string,
    category: string,
    action: string,
    label?: string,
    value?: number,
    metadata?: Record<string, any>
  ): void {
    const analyticsEvent: AnalyticsEvent = {
      event,
      category,
      action,
      label,
      value,
      userId: this.userId,
      sessionId: this.sessionId,
      timestamp: new Date().toISOString(),
      metadata: {
        url: window.location.href,
        referrer: document.referrer,
        user_agent: navigator.userAgent,
        screen_resolution: this.session.screenResolution,
        language: this.session.language,
        timezone: this.session.timezone,
        device_type: this.session.device.type,
        os: this.session.device.os,
        browser: this.session.device.browser,
        utm_source: this.session.utmSource,
        utm_medium: this.session.utmMedium,
        utm_campaign: this.session.utmCampaign,
        country: this.session.country,
        city: this.session.city,
        ...metadata
      }
    };

    this.events.push(analyticsEvent);
    this.session.events++;
    
    // Log in development
    if (import.meta.env.DEV) {
      console.log('📊 Analytics Event:', analyticsEvent);
    }

    // Send to tracking services (with error handling)
    this.sendToServices(analyticsEvent).catch(error => {
      console.warn('Analytics tracking failed:', error);
    });
  }

  private async sendToServices(event: AnalyticsEvent): Promise<void> {
    // Send to Google Analytics 4
    this.sendToGA4(event);
    
    // Send to Google Tag Manager
    this.sendToGTM(event);
    
    // Send to custom backend (only if available and explicitly enabled)
    if (this.backendAvailable) {
      try {
        await this.sendToBackend(event);
      } catch (error) {
        this.backendAvailable = false;
        console.warn('Backend analytics disabled due to connection issues:', error);
      }
    }
    
    // Send to third-party analytics (Mixpanel, Amplitude, etc.)
    this.sendToThirdParty(event);
    
    // Save locally (always works)
    this.saveToLocalStorage(event);
  }

  private sendToGA4(event: AnalyticsEvent): void {
    try {
      if (typeof window !== 'undefined' && (window as any).gtag) {
        (window as any).gtag('event', event.action, {
          event_category: event.category,
          event_label: event.label,
          value: event.value,
          user_id: event.userId,
          session_id: event.sessionId,
          custom_map: event.metadata
        });
      }
    } catch (error) {
      console.warn('GA4 tracking failed:', error);
    }
  }

  private sendToGTM(event: AnalyticsEvent): void {
    try {
      if (typeof window !== 'undefined' && (window as any).dataLayer) {
        (window as any).dataLayer.push({
          event: 'custom_event',
          event_name: event.event,
          event_category: event.category,
          event_action: event.action,
          event_label: event.label,
          event_value: event.value,
          user_id: event.userId,
          session_id: event.sessionId,
          ...event.metadata
        });
      }
    } catch (error) {
      console.warn('GTM tracking failed:', error);
    }
  }

  private async sendToBackend(event: AnalyticsEvent): Promise<void> {
    const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
    const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
    
    if (!supabaseUrl || !supabaseKey) {
      throw new Error('Supabase configuration missing');
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout

    try {
      const response = await fetch(`${supabaseUrl}/functions/v1/analytics-tracker`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...event,
          session: this.session
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      clearTimeout(timeoutId);
      if (error instanceof Error && error.name === 'AbortError') {
        throw new Error('Request timeout');
      }
      throw error;
    }
  }

  private sendToThirdParty(event: AnalyticsEvent): void {
    try {
      // Mixpanel
      if (typeof window !== 'undefined' && (window as any).mixpanel) {
        (window as any).mixpanel.track(event.event, {
          category: event.category,
          action: event.action,
          label: event.label,
          value: event.value,
          ...event.metadata
        });
      }

      // Amplitude
      if (typeof window !== 'undefined' && (window as any).amplitude) {
        (window as any).amplitude.getInstance().logEvent(event.event, {
          category: event.category,
          action: event.action,
          label: event.label,
          value: event.value,
          ...event.metadata
        });
      }

      // Facebook Pixel
      if (typeof window !== 'undefined' && (window as any).fbq) {
        (window as any).fbq('trackCustom', event.event, event.metadata);
      }
    } catch (error) {
      console.warn('Third-party analytics tracking failed:', error);
    }
  }

  private saveToLocalStorage(event: AnalyticsEvent): void {
    try {
      const existingEvents = JSON.parse(localStorage.getItem('analytics_events') || '[]');
      existingEvents.push(event);
      
      // Keep only last 200 events
      if (existingEvents.length > 200) {
        existingEvents.splice(0, existingEvents.length - 200);
      }
      
      localStorage.setItem('analytics_events', JSON.stringify(existingEvents));
    } catch (error) {
      console.warn('Failed to save analytics to localStorage:', error);
    }
  }

  // Method to enable backend analytics if needed
  enableBackendAnalytics(): void {
    this.backendAvailable = true;
  }

  // Enhanced tracking methods
  trackSearch(authorIds: string[], hasCustomApiKey: boolean, yearRange?: string, selectedMetrics?: string[]): void {
    this.track(
      'search_performed',
      'research',
      'author_search',
      `${authorIds.length}_authors`,
      authorIds.length,
      {
        author_ids: authorIds,
        has_custom_api_key: hasCustomApiKey,
        search_type: authorIds.length === 1 ? 'single' : 'multiple',
        search_query_length: authorIds.join(',').length,
        year_range: yearRange,
        selected_metrics: selectedMetrics,
        metrics_count: selectedMetrics?.length
      }
    );
  }

  trackExport(format: 'pdf' | 'excel', authorCount: number, selectedMetrics: string[]): void {
    this.track(
      'export_performed',
      'research',
      'data_export',
      format,
      authorCount,
      {
        export_format: format,
        author_count: authorCount,
        selected_metrics: selectedMetrics,
        metrics_count: selectedMetrics.length,
        export_size_estimate: authorCount * selectedMetrics.length
      }
    );
  }

  trackAuthorIdLookup(method: 'orcid' | 'scholar_profiles', success: boolean): void {
    this.track(
      'author_id_lookup',
      'research',
      'id_lookup',
      method,
      success ? 1 : 0,
      {
        lookup_method: method,
        success,
        lookup_source: method === 'orcid' ? 'api' : 'external_link'
      }
    );
  }

  trackError(errorType: string, errorMessage: string, context?: Record<string, any>): void {
    this.track(
      'error_occurred',
      'error',
      errorType,
      errorMessage.substring(0, 100), // Limit error message length
      undefined,
      {
        error_message: errorMessage,
        error_stack: context?.stack,
        error_context: context
      }
    );
  }

  trackFeatureUsage(feature: string, action: string, details?: Record<string, any>): void {
    this.track(
      'feature_used',
      'engagement',
      action,
      feature,
      undefined,
      {
        feature_name: feature,
        feature_action: action,
        ...details
      }
    );
  }

  // Advanced analytics methods
  getAdvancedAnalyticsSummary(): {
    totalEvents: number;
    searches: number;
    exports: number;
    errors: number;
    sessionDuration: number;
    pageViews: number;
    bounceRate: number;
    topReferrers: Array<{ referrer: string; count: number }>;
    topCountries: Array<{ country: string; count: number }>;
    deviceBreakdown: { desktop: number; mobile: number; tablet: number };
    browserBreakdown: Record<string, number>;
    utmSources: Array<{ source: string; count: number }>;
  } {
    const events = JSON.parse(localStorage.getItem('analytics_events') || '[]');
    const sessions = JSON.parse(localStorage.getItem('completed_sessions') || '[]');
    
    const sessionStart = events.find((e: AnalyticsEvent) => e.action === 'session_start');
    const sessionDuration = sessionStart 
      ? Date.now() - new Date(sessionStart.timestamp).getTime()
      : 0;

    // Calculate bounce rate (sessions with only 1 page view)
    const singlePageSessions = sessions.filter((s: UserSession) => s.pageViews === 1).length;
    const bounceRate = sessions.length > 0 ? (singlePageSessions / sessions.length) * 100 : 0;

    // Top referrers
    const referrerCounts: Record<string, number> = {};
    sessions.forEach((s: UserSession) => {
      const referrer = s.referrer === '' ? 'direct' : new URL(s.referrer || 'direct').hostname;
      referrerCounts[referrer] = (referrerCounts[referrer] || 0) + 1;
    });
    const topReferrers = Object.entries(referrerCounts)
      .map(([referrer, count]) => ({ referrer, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);

    // Top countries
    const countryCounts: Record<string, number> = {};
    sessions.forEach((s: UserSession) => {
      if (s.country) {
        countryCounts[s.country] = (countryCounts[s.country] || 0) + 1;
      }
    });
    const topCountries = Object.entries(countryCounts)
      .map(([country, count]) => ({ country, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);

    // Device breakdown
    const deviceBreakdown = { desktop: 0, mobile: 0, tablet: 0 };
    sessions.forEach((s: UserSession) => {
      deviceBreakdown[s.device.type]++;
    });

    // Browser breakdown
    const browserBreakdown: Record<string, number> = {};
    sessions.forEach((s: UserSession) => {
      browserBreakdown[s.device.browser] = (browserBreakdown[s.device.browser] || 0) + 1;
    });

    // UTM sources
    const utmCounts: Record<string, number> = {};
    sessions.forEach((s: UserSession) => {
      if (s.utmSource) {
        utmCounts[s.utmSource] = (utmCounts[s.utmSource] || 0) + 1;
      }
    });
    const utmSources = Object.entries(utmCounts)
      .map(([source, count]) => ({ source, count }))
      .sort((a, b) => b.count - a.count);

    return {
      totalEvents: events.length,
      searches: events.filter((e: AnalyticsEvent) => e.action === 'author_search').length,
      exports: events.filter((e: AnalyticsEvent) => e.action === 'data_export').length,
      errors: events.filter((e: AnalyticsEvent) => e.category === 'error').length,
      sessionDuration: Math.round(sessionDuration / 1000),
      pageViews: sessions.reduce((sum: number, s: UserSession) => sum + s.pageViews, 0),
      bounceRate: Math.round(bounceRate),
      topReferrers,
      topCountries,
      deviceBreakdown,
      browserBreakdown,
      utmSources
    };
  }

  flush(): void {
    if (this.events.length > 0) {
      console.log(`📊 Flushing ${this.events.length} analytics events`);
      this.events = [];
    }
  }

  exportAnalyticsData(): string {
    const events = JSON.parse(localStorage.getItem('analytics_events') || '[]');
    const sessions = JSON.parse(localStorage.getItem('completed_sessions') || '[]');
    const currentSession = JSON.parse(localStorage.getItem('current_session') || '{}');
    
    return JSON.stringify({
      events,
      sessions,
      currentSession,
      summary: this.getAdvancedAnalyticsSummary(),
      exportedAt: new Date().toISOString()
    }, null, 2);
  }
}

// Create singleton instance
export const analytics = new AdvancedAnalyticsService();

// Helper functions for common tracking scenarios
export const trackPageView = (page: string) => {
  analytics.track('page_view', 'navigation', 'page_view', page);
};

export const trackButtonClick = (buttonName: string, context?: string) => {
  analytics.track('button_click', 'interaction', 'click', buttonName, undefined, { context });
};

export const trackFormSubmission = (formName: string, success: boolean) => {
  analytics.track('form_submission', 'interaction', 'form_submit', formName, success ? 1 : 0);
};