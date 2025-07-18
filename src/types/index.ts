export interface APIResponse {
  dataSource: DataSource;
  results: Result[];
}

export interface DataSource {
  sourceName: string;
  lastUpdated: string;
  metricStartYear: number;
  metricEndYear: number;
}

export interface Result {
  author: Author;
  metrics: Metric[];
}

export interface Author {
  link: Link[];
  name: string;
  uri: string;
}

export interface Link {
  "@href": string;
  "@rel": string;
  "@type": string;
}

export interface Metric {
  metricType: string;
  value?: number;
  valueByYear?: { [year: string]: ValueByYear };
  values?: ThresholdValue[];
}

export interface ValueByYear {
  value: number;
}

export interface ThresholdValue {
  threshold: number;
  percentage: number;
  percentageByYear: { [year: string]: number };
}

export interface ProcessedMetrics {
  hIndex: {
    value: number | string;
    dataSource: DataSource;
  };
  scholarlyOutput: {
    byYear: { [year: string]: number };
    total: number | string;
  };
  fwci: {
    byYear: { [year: string]: number };
    total: number | string;
  };
  topJournal: {
    byYear: { [year: string]: number };
    total: number | string;
  };
  citationCount: {
    byYear: { [year: string]: number };
    total: number | string;
  };
  citationsPerPublication: {
    byYear: { [year: string]: number };
    total: number | string;
  };
  collaboration?: {
    byYear: { [year: string]: number };
    total: number | string;
    collaborationTypes?: {
      institutional?: { byYear: { [year: string]: number }; total: string | number };
      international?: { byYear: { [year: string]: number }; total: string | number };
      national?: { byYear: { [year: string]: number }; total: string | number };
      singleAuthorship?: { byYear: { [year: string]: number }; total: string | number };
    };
  };
  academicCorporateCollaboration?: {
    byYear: { [year: string]: number };
    total: number | string;
    collaborationTypes?: {
      academicCorporate?: { byYear: { [year: string]: number }; total: string | number };
      academicOnly?: { byYear: { [year: string]: number }; total: string | number };
      corporateOnly?: { byYear: { [year: string]: number }; total: string | number };
    };
  };
}

export interface AuthorData {
  dataSource: DataSource;
  metrics: ProcessedMetrics;
  error?: string;
}

export interface MultipleAuthorResult {
  id: string;
  data: AuthorData;
}