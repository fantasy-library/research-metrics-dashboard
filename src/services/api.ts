// Always use direct SciVal API
const API_BASE_URL = 'https://api.elsevier.com/analytics/scival/author/metrics';

const SCIVAL_API_KEY = '7f59af901d2d86f78a1fd60c1bf9426a';

// Rate limiting configuration
const RATE_LIMIT_CONFIG = {
  maxRequestsPerSecond: 2, // Conservative limit - adjust based on your API quota
  maxConcurrentRequests: 3, // Limit concurrent requests
  retryAttempts: 3,
  retryDelay: 2000, // 2 seconds base delay
  backoffMultiplier: 2 // Exponential backoff
};

export interface AuthorMetrics {
  authorName?: string;
  dataSource?: {
    lastUpdated: string;
    sourceName: string;
    metricStartYear: number;
    metricEndYear: number;
    metric: {
      name: string;
      description: string;
    };
  };
  metrics: {
    hIndex: {
      value: string | number;
      dataSource?: any;
    };
    scholarlyOutput: {
      byYear: { [year: string]: number };
      total: string | number;
    };
    fwci: {
      byYear: { [year: string]: number };
      total: string | number;
    };
    topJournal: {
      byYear: { [year: string]: number };
      total: string | number;
    };
    citationCount: {
      byYear: { [year: string]: number };
      total: string | number;
    };
    citationsPerPublication: {
      byYear: { [year: string]: number };
      total: string | number;
    };
    collaboration?: {
      byYear: { [year: string]: number };
      total: string | number;
      collaborationTypes?: {
        institutional?: { byYear: { [year: string]: number }; total: string | number };
        international?: { byYear: { [year: string]: number }; total: string | number };
        national?: { byYear: { [year: string]: number }; total: string | number };
        singleAuthorship?: { byYear: { [year: string]: number }; total: string | number };
      };
    };
    academicCorporateCollaboration?: {
      byYear: { [year: string]: number };
      total: string | number;
      collaborationTypes?: {
        academicCorporate?: { byYear: { [year: string]: number }; total: string | number };
        academicOnly?: { byYear: { [year: string]: number }; total: string | number };
        corporateOnly?: { byYear: { [year: string]: number }; total: string | number };
      };
    };
  };
  error?: string;
}

export class APIError extends Error {
  constructor(
    message: string,
    public statusCode?: number,
    public isEntitlementError: boolean = false,
    public isRateLimitError: boolean = false
  ) {
    super(message);
    this.name = 'APIError';
  }
}

interface FetchParams {
  authors: string;
  metricTypes: string;
  includedDocs: string;
  yearRange: string;
  includeSelfCitations: string;
  byYear: string;
}

function formatParams(params: FetchParams): string {
  return Object.keys(params)
    .map(key => `${encodeURIComponent(key)}=${encodeURIComponent(params[key as keyof FetchParams])}`)
    .join('&');
}

// Helper function to format percentages properly
function formatPercentage(value: number): number {
  const rounded = parseFloat(value.toFixed(2));
  // If the value is a whole number, return it as integer
  return rounded % 1 === 0 ? Math.round(rounded) : rounded;
}

// Rate limiter class
class RateLimiter {
  private requestTimes: number[] = [];
  private activeRequests = 0;
  private requestQueue: Array<() => Promise<void>> = [];
  private processing = false;

  async waitForSlot(): Promise<void> {
    return new Promise((resolve) => {
      this.requestQueue.push(async () => {
        await this.checkRateLimit();
        this.activeRequests++;
        resolve();
      });
      
      if (!this.processing) {
        this.processQueue();
      }
    });
  }

  private async processQueue(): Promise<void> {
    this.processing = true;
    
    while (this.requestQueue.length > 0) {
      if (this.activeRequests >= RATE_LIMIT_CONFIG.maxConcurrentRequests) {
        await new Promise(resolve => setTimeout(resolve, 100));
        continue;
      }
      
      const request = this.requestQueue.shift();
      if (request) {
        await request();
      }
    }
    
    this.processing = false;
  }

  private async checkRateLimit(): Promise<void> {
    const now = Date.now();
    const oneSecondAgo = now - 1000;
    
    // Remove requests older than 1 second
    this.requestTimes = this.requestTimes.filter(time => time > oneSecondAgo);
    
    // If we're at the rate limit, wait
    if (this.requestTimes.length >= RATE_LIMIT_CONFIG.maxRequestsPerSecond) {
      const oldestRequest = Math.min(...this.requestTimes);
      const waitTime = 1000 - (now - oldestRequest) + 100; // Add 100ms buffer
      
      if (waitTime > 0) {
        await new Promise(resolve => setTimeout(resolve, waitTime));
      }
    }
    
    this.requestTimes.push(now);
  }

  releaseSlot(): void {
    this.activeRequests = Math.max(0, this.activeRequests - 1);
  }
}

// Global rate limiter instance
const rateLimiter = new RateLimiter();

// Retry with exponential backoff
async function retryWithBackoff<T>(
  operation: () => Promise<T>,
  maxAttempts: number = RATE_LIMIT_CONFIG.retryAttempts,
  baseDelay: number = RATE_LIMIT_CONFIG.retryDelay
): Promise<T> {
  let lastError: Error;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await operation();
    } catch (error) {
      lastError = error as Error;
      
      // Don't retry on non-rate-limit errors after first attempt
      if (error instanceof APIError && !error.isRateLimitError && attempt > 1) {
        throw error;
      }
      
      // Don't retry on the last attempt
      if (attempt === maxAttempts) {
        break;
      }
      
      // Calculate delay with exponential backoff
      const delay = baseDelay * Math.pow(RATE_LIMIT_CONFIG.backoffMultiplier, attempt - 1);
      const jitter = Math.random() * 1000; // Add random jitter to avoid thundering herd
      
      console.log(`Attempt ${attempt} failed, retrying in ${delay + jitter}ms...`);
      await new Promise(resolve => setTimeout(resolve, delay + jitter));
    }
  }
  
  throw lastError!;
}

export class APIService {
  private async fetchDirectMetric(authorId: string, metricType: string, byYear: boolean, customApiKey?: string, yearRange: string = '5yrs', includeSelfCitations: string = 'false', includedDocs: string = 'AllPublicationTypes'): Promise<any> {
    const apiKey = customApiKey || SCIVAL_API_KEY;
    
    if (!apiKey) {
      throw new APIError('SciVal API key is not configured. Please provide an API key or check your environment variables.');
    }

    const params: FetchParams = {
      authors: authorId,
      metricTypes: metricType,
      includedDocs: includedDocs,
      yearRange: yearRange,
      includeSelfCitations: includeSelfCitations,
      byYear: byYear.toString()
    };
    
    const url = `${API_BASE_URL}?${formatParams(params)}`;
    
    return retryWithBackoff(async () => {
      await rateLimiter.waitForSlot();
      
      try {
        const response = await fetch(url, {
          method: 'GET',
          headers: {
            'Accept': 'application/json',
            'X-ELS-APIKey': apiKey,
            'User-Agent': 'SciVal-Research-Dashboard/1.0'
          }
        });
        
        if (!response.ok) {
          const errorText = await response.text();
          let isEntitlementError = false;
          let isRateLimitError = false;
          let errorMessage = `API Error (${response.status}): ${errorText}`;

          // Check for different error types
          if (response.status === 429 || errorText.includes('RATE_LIMIT_EXCEEDED')) {
            isRateLimitError = true;
            errorMessage = 'Rate limit exceeded. The system will automatically retry your request. Please wait...';
          } else if (errorText.includes('ENTITLEMENTS_ERROR') || 
                     errorText.includes('Not entitled to the resource')) {
            isEntitlementError = true;
            errorMessage = 'API Access Error: Your SciVal API key does not have the required permissions to access this resource. Please contact your administrator to verify your API key has the necessary entitlements for SciVal author metrics.';
          }

          throw new APIError(errorMessage, response.status, isEntitlementError, isRateLimitError);
        }
        
        return await response.json();
      } finally {
        rateLimiter.releaseSlot();
      }
    });
  }

  private processHIndex(data: any) {
    return {
      value: data.results?.[0]?.metrics?.[0]?.value || 'N/A',
      dataSource: data.dataSource
    };
  }

  private processScholarlyOutput(yearData: any, totalData: any) {
    const byYear = yearData.results?.[0]?.metrics?.[0]?.valueByYear || {};
    return {
      byYear: this.normalizeYearData(byYear),
      total: totalData.results?.[0]?.metrics?.[0]?.value || 'N/A'
    };
  }

  private processFWCI(yearData: any, totalData: any) {
    const byYear = yearData.results?.[0]?.metrics?.[0]?.valueByYear || {};
    return {
      byYear: this.normalizeYearData(byYear),
      total: totalData.results?.[0]?.metrics?.[0]?.value || 'N/A'
    };
  }

  private processTopJournal(yearData: any, totalData: any) {
    const thresholdData = yearData.results?.[0]?.metrics?.[0]?.values?.find((v: any) => v.threshold === 10);
    const totalThreshold = totalData.results?.[0]?.metrics?.[0]?.values?.find((v: any) => v.threshold === 10);
    
    return {
      byYear: thresholdData?.percentageByYear || {},
      total: totalThreshold?.percentage || 'N/A'
    };
  }

  private processCitations(yearData: any, totalData: any) {
    const byYear = yearData.results?.[0]?.metrics?.[0]?.valueByYear || {};
    return {
      byYear: this.normalizeYearData(byYear),
      total: totalData.results?.[0]?.metrics?.[0]?.value || 'N/A'
    };
  }

  private processCollaboration(data: any) {
    const metric = data.results?.[0]?.metrics?.[0];
    if (!metric || !metric.values) {
      return {
        byYear: {},
        total: 'N/A',
        collaborationTypes: {
          institutional: { byYear: {}, total: 'N/A' },
          international: { byYear: {}, total: 'N/A' },
          national: { byYear: {}, total: 'N/A' },
          singleAuthorship: { byYear: {}, total: 'N/A' }
        }
      };
    }

    const collaborationTypes: any = {
      institutional: { byYear: {}, total: 'N/A' },
      international: { byYear: {}, total: 'N/A' },
      national: { byYear: {}, total: 'N/A' },
      singleAuthorship: { byYear: {}, total: 'N/A' }
    };

    let totalByYear: { [year: string]: number } = {};

    metric.values.forEach((collabData: any) => {
      const collabType = collabData.collabType?.toLowerCase();
      
      // Use percentageByYear for collaboration data
      if (collabData.percentageByYear) {
        const normalizedData = this.normalizeYearDataWithFormatting(collabData.percentageByYear);
        
        // Calculate total percentage (average across years)
        const values = Object.values(normalizedData);
        const total = values.length > 0 ? formatPercentage(values.reduce((sum: number, val: number) => sum + val, 0) / values.length) : 'N/A';
        
        if (collabType?.includes('institutional')) {
          collaborationTypes.institutional = { byYear: normalizedData, total };
        } else if (collabType?.includes('international')) {
          collaborationTypes.international = { byYear: normalizedData, total };
        } else if (collabType?.includes('national')) {
          collaborationTypes.national = { byYear: normalizedData, total };
        } else if (collabType?.includes('single')) {
          collaborationTypes.singleAuthorship = { byYear: normalizedData, total };
        }

        // For the main display, show international collaboration as it's typically the most significant
        if (collabType?.includes('international')) {
          totalByYear = normalizedData;
        }
      }
    });

    // Calculate grand total as average percentage for international collaboration
    const totalValues = Object.values(totalByYear);
    const grandTotal = totalValues.length > 0 ? formatPercentage(totalValues.reduce((sum: number, val: number) => sum + val, 0) / totalValues.length) : 'N/A';

    return {
      byYear: totalByYear, // Show international collaboration percentages as main metric
      total: grandTotal,
      collaborationTypes
    };
  }

  private processAcademicCorporateCollaboration(data: any) {
    const metric = data.results?.[0]?.metrics?.[0];
    if (!metric || !metric.values) {
      return {
        byYear: {},
        total: 'N/A',
        collaborationTypes: {
          academicCorporate: { byYear: {}, total: 'N/A' },
          academicOnly: { byYear: {}, total: 'N/A' },
          corporateOnly: { byYear: {}, total: 'N/A' }
        }
      };
    }

    const collaborationTypes: any = {
      academicCorporate: { byYear: {}, total: 'N/A' },
      academicOnly: { byYear: {}, total: 'N/A' },
      corporateOnly: { byYear: {}, total: 'N/A' }
    };

    let totalByYear: { [year: string]: number } = {};

    metric.values.forEach((collabData: any) => {
      const collabType = collabData.collabType?.toLowerCase();
      
      // Use percentageByYear for collaboration data
      if (collabData.percentageByYear) {
        const normalizedData = this.normalizeYearDataWithFormatting(collabData.percentageByYear);
        
        // Calculate total percentage (average across years)
        const values = Object.values(normalizedData);
        const total = values.length > 0 ? formatPercentage(values.reduce((sum: number, val: number) => sum + val, 0) / values.length) : 'N/A';
        
        if (collabType?.includes('academic-corporate')) {
          collaborationTypes.academicCorporate = { byYear: normalizedData, total };
          totalByYear = normalizedData; // Use academic-corporate as main metric
        } else if (collabType?.includes('academic only')) {
          collaborationTypes.academicOnly = { byYear: normalizedData, total };
        } else if (collabType?.includes('corporate only')) {
          collaborationTypes.corporateOnly = { byYear: normalizedData, total };
        }
      }
    });

    // Calculate grand total as average percentage for academic-corporate collaboration
    const totalValues = Object.values(totalByYear);
    const grandTotal = totalValues.length > 0 ? formatPercentage(totalValues.reduce((sum: number, val: number) => sum + val, 0) / totalValues.length) : 'N/A';

    return {
      byYear: totalByYear,
      total: grandTotal,
      collaborationTypes
    };
  }

  private normalizeYearData(yearData: any) {
    const normalized: { [key: string]: number } = {};
    
    // Process all years present in the data, don't limit to hardcoded range
    for (const [yearStr, value] of Object.entries(yearData)) {
      const year = parseInt(yearStr);
      if (!isNaN(year)) {
        if (typeof value === 'object' && value !== null && 'value' in value) {
          normalized[yearStr] = parseFloat(((value as any).value).toFixed(2));
        } else if (typeof value === 'number') {
          normalized[yearStr] = parseFloat(value.toFixed(2));
        } else {
          normalized[yearStr] = 0;
        }
      }
    }
    
    return normalized;
  }

  private normalizeYearDataWithFormatting(yearData: any) {
    const normalized: { [key: string]: number } = {};
    
    // Process all years present in the data with proper percentage formatting
    for (const [yearStr, value] of Object.entries(yearData)) {
      const year = parseInt(yearStr);
      if (!isNaN(year)) {
        if (typeof value === 'object' && value !== null && 'value' in value) {
          normalized[yearStr] = formatPercentage((value as any).value);
        } else if (typeof value === 'number') {
          normalized[yearStr] = formatPercentage(value);
        } else {
          normalized[yearStr] = 0;
        }
      }
    }
    
    return normalized;
  }

  private extractAuthorName(data: any): string | undefined {
    // Extract author name from the first result
    const authorName = data.results?.[0]?.author?.name;
    return authorName || undefined;
  }

  private async getDirectAuthorMetrics(authorId: string, customApiKey?: string, yearRange: string = '5yrs', availableMetrics?: any[], includedDocs: string = 'AllPublicationTypes', includeSelfCitations: boolean = true): Promise<AuthorMetrics> {
    try {
      // Processing author metrics
      
      // Determine which metrics to fetch based on enabled metrics
      const enabledMetrics = availableMetrics?.filter(m => m.enabled) || [];
      const enabledMetricIds = enabledMetrics.map(m => m.id);
      
      // Always fetch H-Index as it's a base metric
      const hIndexData = await this.fetchDirectMetric(authorId, 'HIndices', false, customApiKey, yearRange, includeSelfCitations.toString(), includedDocs);
      
      let soYearData, soTotalData, fwciYearData, fwciTotalData, topJData, topJTotalData;
      let citationCountYearData, citationCountTotalData, citationsPerPublicationYearData, citationsPerPublicationTotalData;
      let collaborationData, academicCorporateCollaborationData;

      // Fetch metrics based on what's enabled
      if (enabledMetricIds.includes('publication')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        soYearData = await this.fetchDirectMetric(authorId, 'ScholarlyOutput', true, customApiKey, yearRange, 'false', includedDocs);
        
        await new Promise(resolve => setTimeout(resolve, 200));
        soTotalData = await this.fetchDirectMetric(authorId, 'ScholarlyOutput', false, customApiKey, yearRange, 'false', includedDocs);
      }

      if (enabledMetricIds.includes('fwci')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        fwciYearData = await this.fetchDirectMetric(authorId, 'FieldWeightedCitationImpact', true, customApiKey, yearRange, 'false', includedDocs);
        
        await new Promise(resolve => setTimeout(resolve, 200));
        fwciTotalData = await this.fetchDirectMetric(authorId, 'FieldWeightedCitationImpact', false, customApiKey, yearRange, 'false', includedDocs);
      }

      if (enabledMetricIds.includes('topJournal')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        topJData = await this.fetchDirectMetric(authorId, 'PublicationsInTopJournalPercentiles', true, customApiKey, yearRange, 'false', includedDocs);
        
        await new Promise(resolve => setTimeout(resolve, 200));
        topJTotalData = await this.fetchDirectMetric(authorId, 'PublicationsInTopJournalPercentiles', false, customApiKey, yearRange, 'false', includedDocs);
      }

      if (enabledMetricIds.includes('citationCount')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        citationCountYearData = await this.fetchDirectMetric(authorId, 'CitationCount', true, customApiKey, yearRange, includeSelfCitations.toString(), includedDocs);
        
        await new Promise(resolve => setTimeout(resolve, 200));
        citationCountTotalData = await this.fetchDirectMetric(authorId, 'CitationCount', false, customApiKey, yearRange, includeSelfCitations.toString(), includedDocs);
      }

      if (enabledMetricIds.includes('citationsPerPublication')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        citationsPerPublicationYearData = await this.fetchDirectMetric(authorId, 'CitationsPerPublication', true, customApiKey, yearRange, includeSelfCitations.toString(), includedDocs);
        
        await new Promise(resolve => setTimeout(resolve, 200));
        citationsPerPublicationTotalData = await this.fetchDirectMetric(authorId, 'CitationsPerPublication', false, customApiKey, yearRange, includeSelfCitations.toString(), includedDocs);
      }

      // Fetch collaboration metrics
      if (enabledMetricIds.includes('collaboration')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        collaborationData = await this.fetchDirectMetric(authorId, 'Collaboration', true, customApiKey, yearRange, 'false', includedDocs);
      }

      // Fetch academic corporate collaboration metrics
      if (enabledMetricIds.includes('academicCorporateCollaboration')) {
        await new Promise(resolve => setTimeout(resolve, 200));
        academicCorporateCollaborationData = await this.fetchDirectMetric(authorId, 'AcademicCorporateCollaboration', true, customApiKey, yearRange, 'false', includedDocs);
      }

      // Extract author name from any of the responses
      const authorName = this.extractAuthorName(hIndexData) || 
                        this.extractAuthorName(soYearData) || 
                        this.extractAuthorName(soTotalData);

      const metrics: any = {
        hIndex: this.processHIndex(hIndexData)
      };

      // Only include metrics that were fetched
      if (soYearData && soTotalData) {
        metrics.scholarlyOutput = this.processScholarlyOutput(soYearData, soTotalData);
      } else {
        metrics.scholarlyOutput = { byYear: {}, total: 'N/A' };
      }

      if (fwciYearData && fwciTotalData) {
        metrics.fwci = this.processFWCI(fwciYearData, fwciTotalData);
      } else {
        metrics.fwci = { byYear: {}, total: 'N/A' };
      }

      if (topJData && topJTotalData) {
        metrics.topJournal = this.processTopJournal(topJData, topJTotalData);
      } else {
        metrics.topJournal = { byYear: {}, total: 'N/A' };
      }

      if (citationCountYearData && citationCountTotalData) {
        metrics.citationCount = this.processCitations(citationCountYearData, citationCountTotalData);
      } else {
        metrics.citationCount = { byYear: {}, total: 'N/A' };
      }

      if (citationsPerPublicationYearData && citationsPerPublicationTotalData) {
        metrics.citationsPerPublication = this.processCitations(citationsPerPublicationYearData, citationsPerPublicationTotalData);
      } else {
        metrics.citationsPerPublication = { byYear: {}, total: 'N/A' };
      }

      // Process collaboration metrics
      if (collaborationData) {
        metrics.collaboration = this.processCollaboration(collaborationData);
      } else {
        metrics.collaboration = { byYear: {}, total: 'N/A' };
      }

      // Process academic corporate collaboration metrics
      if (academicCorporateCollaborationData) {
        metrics.academicCorporateCollaboration = this.processAcademicCorporateCollaboration(academicCorporateCollaborationData);
      } else {
        metrics.academicCorporateCollaboration = { byYear: {}, total: 'N/A' };
      }

      return {
        authorName,
        dataSource: {
          ...hIndexData.dataSource,
          sourceName: hIndexData.dataSource?.sourceName || 'SciVal',
          lastUpdated: hIndexData.dataSource?.lastUpdated || new Date().toISOString(),
          metricStartYear: hIndexData.dataSource?.metricStartYear || 2020,
          metricEndYear: hIndexData.dataSource?.metricEndYear || new Date().getFullYear()
        },
        metrics
      };
    } catch (e) {
      console.error(`Error processing ${authorId}:`, e);
      throw e;
    }
  }

  async getAuthorMetrics(authorId: string, customApiKey?: string, yearRange: string = '5yrs', availableMetrics?: any[], includedDocs: string = 'AllPublicationTypes', includeSelfCitations: boolean = true): Promise<AuthorMetrics> {
    try {
      return await this.getDirectAuthorMetrics(authorId, customApiKey, yearRange, availableMetrics, includedDocs, includeSelfCitations);
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new APIError(`Error processing ${authorId}: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async processMultipleAuthors(authorIds: string[], customApiKey?: string, yearRange: string = '5yrs', availableMetrics?: any[], includedDocs: string = 'AllPublicationTypes', includeSelfCitations: boolean = true): Promise<Array<{id: string, data: AuthorMetrics}>> {
    try {
      // Process authors sequentially to avoid overwhelming the API
      const results: Array<{id: string, data: AuthorMetrics}> = [];
      
      for (const authorId of authorIds) {
        try {
          // Processing author ${authorId} (${results.length + 1}/${authorIds.length})
          const data = await this.getDirectAuthorMetrics(authorId.trim(), customApiKey, yearRange, availableMetrics, includedDocs, includeSelfCitations);
          results.push({ id: authorId.trim(), data });
          
          // Add delay between authors to be extra safe
          if (results.length < authorIds.length) {
            await new Promise(resolve => setTimeout(resolve, 1000));
          }
        } catch (error) {
          console.error(`Error processing author ${authorId}:`, error);
          results.push({
            id: authorId.trim(),
            data: {
              error: error instanceof Error ? error.message : 'Unknown error',
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
            }
          });
        }
      }
      
      return results;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }
      throw new APIError(`Error processing multiple authors: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }
}

export const apiService = new APIService();