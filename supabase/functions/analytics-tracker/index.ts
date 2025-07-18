const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

interface AnalyticsEvent {
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

interface UserSession {
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

interface AnalyticsPayload {
  event?: AnalyticsEvent;
  session?: UserSession;
  events?: AnalyticsEvent[];
}

// Helper function to get client IP
function getClientIP(request: Request): string {
  const xForwardedFor = request.headers.get('x-forwarded-for');
  const xRealIP = request.headers.get('x-real-ip');
  const cfConnectingIP = request.headers.get('cf-connecting-ip');
  
  return xForwardedFor?.split(',')[0] || xRealIP || cfConnectingIP || 'unknown';
}

// Helper function to get geographic data from IP
async function getGeoDataFromIP(ip: string): Promise<{ country?: string; city?: string }> {
  try {
    // In production, you might want to use a more reliable service
    // or integrate with Supabase's built-in geolocation features
    const response = await fetch(`https://ipapi.co/${ip}/json/`);
    if (response.ok) {
      const data = await response.json();
      return {
        country: data.country_name,
        city: data.city
      };
    }
  } catch (error) {
    console.warn('Failed to get geo data:', error);
  }
  return {};
}

// Helper function to detect bot/crawler
function isBot(userAgent: string): boolean {
  const botPatterns = [
    /bot/i, /crawler/i, /spider/i, /scraper/i,
    /googlebot/i, /bingbot/i, /slurp/i, /duckduckbot/i,
    /baiduspider/i, /yandexbot/i, /facebookexternalhit/i,
    /twitterbot/i, /linkedinbot/i, /whatsapp/i,
    /telegram/i, /skype/i, /zoom/i
  ];
  
  return botPatterns.some(pattern => pattern.test(userAgent));
}

// Helper function to validate and sanitize data
function sanitizeEvent(event: AnalyticsEvent): AnalyticsEvent {
  return {
    event: event.event?.substring(0, 100) || 'unknown',
    category: event.category?.substring(0, 50) || 'unknown',
    action: event.action?.substring(0, 100) || 'unknown',
    label: event.label?.substring(0, 200),
    value: typeof event.value === 'number' ? event.value : undefined,
    userId: event.userId?.substring(0, 100),
    sessionId: event.sessionId?.substring(0, 100),
    timestamp: event.timestamp || new Date().toISOString(),
    metadata: event.metadata ? JSON.parse(JSON.stringify(event.metadata).substring(0, 2000)) : undefined
  };
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 200,
        headers: corsHeaders,
      });
    }

    if (req.method !== "POST") {
      return new Response(
        JSON.stringify({ error: "Method not allowed" }),
        {
          status: 405,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    const payload: AnalyticsPayload = await req.json();
    const clientIP = getClientIP(req);
    const userAgent = req.headers.get('user-agent') || 'unknown';
    
    // Filter out bots and crawlers
    if (isBot(userAgent)) {
      return new Response(
        JSON.stringify({ success: true, message: "Bot traffic filtered" }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // Get geographic data
    const geoData = await getGeoDataFromIP(clientIP);

    // Process single event
    if (payload.event) {
      const sanitizedEvent = sanitizeEvent(payload.event);
      
      // Enrich event with server-side data
      const enrichedEvent = {
        ...sanitizedEvent,
        serverTimestamp: new Date().toISOString(),
        clientIP: clientIP,
        serverUserAgent: userAgent,
        ...geoData
      };

      // Log the event (in production, save to database)
      console.log('📊 Analytics Event:', JSON.stringify(enrichedEvent, null, 2));

      // Here you would typically:
      // 1. Save to Supabase database
      // 2. Send to external analytics services (Google Analytics, Mixpanel, etc.)
      // 3. Update real-time dashboards
      // 4. Trigger alerts for critical events

      // Example database save (uncomment when you have the table set up):
      /*
      const { data, error } = await supabase
        .from('analytics_events')
        .insert([enrichedEvent]);
      
      if (error) {
        console.error('Database save error:', error);
      }
      */
    }

    // Process session data
    if (payload.session) {
      const enrichedSession = {
        ...payload.session,
        serverTimestamp: new Date().toISOString(),
        clientIP: clientIP,
        ...geoData
      };

      console.log('👤 Session Data:', JSON.stringify(enrichedSession, null, 2));

      // Save session data to database
      /*
      const { data, error } = await supabase
        .from('user_sessions')
        .upsert([enrichedSession], { onConflict: 'sessionId' });
      */
    }

    // Process batch events
    if (payload.events && Array.isArray(payload.events)) {
      const enrichedEvents = payload.events.map(event => ({
        ...sanitizeEvent(event),
        serverTimestamp: new Date().toISOString(),
        clientIP: clientIP,
        serverUserAgent: userAgent,
        ...geoData
      }));

      console.log(`📊 Batch Events (${enrichedEvents.length}):`, JSON.stringify(enrichedEvents, null, 2));

      // Batch save to database
      /*
      const { data, error } = await supabase
        .from('analytics_events')
        .insert(enrichedEvents);
      */
    }

    // Send to external services (Google Analytics, etc.)
    // This is where you'd integrate with GA4, Mixpanel, Amplitude, etc.
    
    // Example: Send to Google Analytics Measurement Protocol
    /*
    if (payload.event) {
      try {
        await fetch('https://www.google-analytics.com/mp/collect', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            client_id: payload.event.userId,
            events: [{
              name: payload.event.event,
              params: {
                event_category: payload.event.category,
                event_label: payload.event.label,
                value: payload.event.value,
                ...payload.event.metadata
              }
            }]
          })
        });
      } catch (error) {
        console.warn('Failed to send to GA4:', error);
      }
    }
    */

    return new Response(
      JSON.stringify({ 
        success: true, 
        message: "Analytics data processed successfully",
        eventId: `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        processed: {
          event: !!payload.event,
          session: !!payload.session,
          batchEvents: payload.events?.length || 0
        }
      }),
      {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );

  } catch (error) {
    console.error('Error in analytics-tracker:', error);
    return new Response(
      JSON.stringify({ 
        error: `Server Error: ${error instanceof Error ? error.message : 'Unknown error'}` 
      }),
      {
        status: 500,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
});