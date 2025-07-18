const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization, X-ELS-APIKey",
};

// Use environment variable for API key
const DEFAULT_API_KEY = '7f59af901d2d86f78a1fd60c1bf9426a';
const BASE_URL = 'https://api.elsevier.com/analytics/scival/author/metrics';

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

async function fetchMetric(authorId: string, metricType: string, byYear: boolean, customApiKey?: string, yearRange: string = '5yrs', includeSelfCitations: string = 'false', includedDocs: string = 'AllPublicationTypes') {
  const apiKey = customApiKey || DEFAULT_API_KEY;
  
  if (!apiKey) {
    throw new Error('SCIVAL_API_KEY environment variable is not set and no custom API key provided');
  }

  const params: FetchParams = {
    authors: authorId,
    metricTypes: metricType,
    includedDocs: includedDocs,
    yearRange: yearRange,
    includeSelfCitations: includeSelfCitations,
    byYear: byYear.toString()
  };
  
  const url = `${BASE_URL}?${formatParams(params)}`;
  
  // Use headers similar to Google Apps Script
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
    console.error(`API Error (${response.status}):`, errorText);
    throw new Error(`API Error (${response.status}): ${errorText}`);
  }
  
  return await response.json();
}

function processHIndex(data: any) {
  return {
    value: data.results[0]?.metrics[0]?.value || 'N/A',
    dataSource: data.dataSource
  };
}

function processScholarlyOutput(yearData: any, totalData: any) {
  const byYear = yearData.results[0]?.metrics[0]?.valueByYear || {};
  return {
    byYear: normalizeYearData(byYear),
    total: totalData.results[0]?.metrics[0]?.value || 'N/A'
  };
}

function processFWCI(yearData: any, totalData: any) {
  const byYear = yearData.results[0]?.metrics[0]?.valueByYear || {};
  return {
    byYear: normalizeYearData(byYear),
    total: totalData.results[0]?.metrics[0]?.value || 'N/A'
  };
}

function processTopJournal(yearData: any, totalData: any) {
  const thresholdData = yearData.results[0]?.metrics[0]?.values?.find((v: any) => v.threshold === 10);
  const totalThreshold = totalData.results[0]?.metrics[0]?.values?.find((v: any) => v.threshold === 10);
  
  return {
    byYear: thresholdData?.percentageByYear || {},
    total: totalThreshold?.percentage || 'N/A'
  };
}

function processCitations(yearData: any, totalData: any) {
  const byYear = yearData.results[0]?.metrics[0]?.valueByYear || {};
  return {
    byYear: normalizeYearData(byYear),
    total: totalData.results[0]?.metrics[0]?.value || 'N/A'
  };
}

function processCollaboration(data: any) {
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
      const normalizedData = normalizeYearDataWithFormatting(collabData.percentageByYear);
      
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

function processAcademicCorporateCollaboration(data: any) {
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
      const normalizedData = normalizeYearDataWithFormatting(collabData.percentageByYear);
      
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

function normalizeYearData(yearData: any) {
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

function normalizeYearDataWithFormatting(yearData: any) {
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

function extractAuthorName(data: any): string | undefined {
  // Extract author name from the first result
  const authorName = data.results?.[0]?.author?.name;
  return authorName || undefined;
}

async function getAuthorMetrics(authorId: string, customApiKey?: string, yearRange: string = '5yrs', availableMetrics?: any[], includedDocs: string = 'AllPublicationTypes') {
  try {
    console.log(`Processing author: ${authorId} with year range: ${yearRange}, document types: ${includedDocs}`);
    
    // Determine which metrics to fetch based on enabled metrics
    const enabledMetrics = availableMetrics?.filter(m => m.enabled) || [];
    const enabledMetricIds = enabledMetrics.map(m => m.id);
    
    // Always fetch H-Index as it's a base metric
    const hIndexData = await fetchMetric(authorId, 'HIndices', false, customApiKey, yearRange, 'false', includedDocs);
    
    let soYearData, soTotalData, fwciYearData, fwciTotalData, topJData, topJTotalData;
    let citationYearData, citationTotalData, citationInclYearData, citationInclTotalData;
    let collaborationData, academicCorporateCollaborationData;

    // Fetch metrics based on what's enabled
    if (enabledMetricIds.includes('publication')) {
      soYearData = await fetchMetric(authorId, 'ScholarlyOutput', true, customApiKey, yearRange, 'false', includedDocs);
      soTotalData = await fetchMetric(authorId, 'ScholarlyOutput', false, customApiKey, yearRange, 'false', includedDocs);
    }

    if (enabledMetricIds.includes('fwci')) {
      fwciYearData = await fetchMetric(authorId, 'FieldWeightedCitationImpact', true, customApiKey, yearRange, 'false', includedDocs);
      fwciTotalData = await fetchMetric(authorId, 'FieldWeightedCitationImpact', false, customApiKey, yearRange, 'false', includedDocs);
    }

    if (enabledMetricIds.includes('topJournal')) {
      topJData = await fetchMetric(authorId, 'PublicationsInTopJournalPercentiles', true, customApiKey, yearRange, 'false', includedDocs);
      topJTotalData = await fetchMetric(authorId, 'PublicationsInTopJournalPercentiles', false, customApiKey, yearRange, 'false', includedDocs);
    }

    if (enabledMetricIds.includes('citations')) {
      citationYearData = await fetchMetric(authorId, 'CitationCount', true, customApiKey, yearRange, 'false', includedDocs);
      citationTotalData = await fetchMetric(authorId, 'CitationCount', false, customApiKey, yearRange, 'false', includedDocs);
    }

    if (enabledMetricIds.includes('citationsIncl')) {
      citationInclYearData = await fetchMetric(authorId, 'CitationCount', true, customApiKey, yearRange, 'true', includedDocs);
      citationInclTotalData = await fetchMetric(authorId, 'CitationCount', false, customApiKey, yearRange, 'true', includedDocs);
    }

    // Fetch collaboration metrics
    if (enabledMetricIds.includes('collaboration')) {
      collaborationData = await fetchMetric(authorId, 'Collaboration', true, customApiKey, yearRange, 'false', includedDocs);
    }

    // Fetch academic corporate collaboration metrics
    if (enabledMetricIds.includes('academicCorporateCollaboration')) {
      academicCorporateCollaborationData = await fetchMetric(authorId, 'AcademicCorporateCollaboration', true, customApiKey, yearRange, 'false', includedDocs);
    }

    // Extract author name from any of the responses
    const authorName = extractAuthorName(hIndexData) || 
                      extractAuthorName(soYearData) || 
                      extractAuthorName(soTotalData);

    const metrics: any = {
      hIndex: processHIndex(hIndexData)
    };

    // Only include metrics that were fetched
    if (soYearData && soTotalData) {
      metrics.scholarlyOutput = processScholarlyOutput(soYearData, soTotalData);
    } else {
      metrics.scholarlyOutput = { byYear: {}, total: 'N/A' };
    }

    if (fwciYearData && fwciTotalData) {
      metrics.fwci = processFWCI(fwciYearData, fwciTotalData);
    } else {
      metrics.fwci = { byYear: {}, total: 'N/A' };
    }

    if (topJData && topJTotalData) {
      metrics.topJournal = processTopJournal(topJData, topJTotalData);
    } else {
      metrics.topJournal = { byYear: {}, total: 'N/A' };
    }

    if (citationYearData && citationTotalData) {
      metrics.citations = processCitations(citationYearData, citationTotalData);
    } else {
      metrics.citations = { byYear: {}, total: 'N/A' };
    }

    if (citationInclYearData && citationInclTotalData) {
      metrics.citationsIncl = processCitations(citationInclYearData, citationInclTotalData);
    } else {
      metrics.citationsIncl = { byYear: {}, total: 'N/A' };
    }

    // Process collaboration metrics
    if (collaborationData) {
      metrics.collaboration = processCollaboration(collaborationData);
    } else {
      metrics.collaboration = { byYear: {}, total: 'N/A' };
    }

    // Process academic corporate collaboration metrics
    if (academicCorporateCollaborationData) {
      metrics.academicCorporateCollaboration = processAcademicCorporateCollaboration(academicCorporateCollaborationData);
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
    return { error: e instanceof Error ? e.message : 'Unknown error' };
  }
}

async function processMultipleAuthors(authorIds: string[], customApiKey?: string, yearRange: string = '5yrs', availableMetrics?: any[], includedDocs: string = 'AllPublicationTypes') {
  const results = await Promise.allSettled(
    authorIds.map(async (id) => ({
      id: id.trim(),
      data: await getAuthorMetrics(id.trim(), customApiKey, yearRange, availableMetrics, includedDocs)
    }))
  );

  return results.map((result, index) => ({
    id: authorIds[index].trim(),
    data: result.status === 'fulfilled' ? result.value.data : { error: result.reason?.message || 'Unknown error' }
  }));
}

Deno.serve(async (req: Request) => {
  try {
    if (req.method === "OPTIONS") {
      return new Response(null, {
        status: 200,
        headers: corsHeaders,
      });
    }

    if (req.method !== "GET" && req.method !== "POST") {
      return new Response(
        JSON.stringify({ error: "Method not allowed" }),
        {
          status: 405,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    const url = new URL(req.url);
    
    // Handle single metric requests (for debugging)
    if (req.method === "GET") {
      const authorId = url.searchParams.get('authors');
      const metricType = url.searchParams.get('metricTypes');
      const byYear = url.searchParams.get('byYear');
      const customApiKey = url.searchParams.get('apiKey');
      const yearRange = url.searchParams.get('yearRange') || '5yrs';
      const includeSelfCitations = url.searchParams.get('includeSelfCitations') || 'false';
      const includedDocs = url.searchParams.get('includedDocs') || 'AllPublicationTypes';

      if (!authorId || !metricType || !byYear) {
        return new Response(
          JSON.stringify({ error: "Missing required parameters: authors, metricTypes, byYear" }),
          {
            status: 400,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }

      const data = await fetchMetric(authorId, metricType, byYear === 'true', customApiKey || undefined, yearRange, includeSelfCitations, includedDocs);
      
      return new Response(
        JSON.stringify(data),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // Handle complete author metrics or multiple authors request
    if (req.method === "POST") {
      const body = await req.json();
      const customApiKey = body.customApiKey;
      const yearRange = body.yearRange || '5yrs';
      const availableMetrics = body.availableMetrics;
      const includedDocs = body.includedDocs || 'AllPublicationTypes';
      
      if (body.action === 'getAuthorMetrics' && body.authorId) {
        const data = await getAuthorMetrics(body.authorId, customApiKey, yearRange, availableMetrics, includedDocs);
        return new Response(
          JSON.stringify(data),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }
      
      if (body.action === 'processMultipleAuthors' && body.authorIds) {
        const data = await processMultipleAuthors(body.authorIds, customApiKey, yearRange, availableMetrics, includedDocs);
        return new Response(
          JSON.stringify(data),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }
      
      return new Response(
        JSON.stringify({ error: "Invalid request body" }),
        {
          status: 400,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

  } catch (error) {
    console.error('Error in scival-proxy:', error);
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