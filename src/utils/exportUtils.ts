import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import * as XLSX from 'xlsx';
import { ProcessedMetrics } from '../types';

export interface ExportData {
  authorId: string;
  authorName?: string;
  metrics: ProcessedMetrics;
  dataSource?: {
    sourceName: string;
    lastUpdated: string;
    metricStartYear: number;
    metricEndYear: number;
  };
  selectedMetrics?: string[];
  metricOrder?: string[];
}

interface MetricDefinition {
  id: string;
  label: string;
  getData: (metrics: ProcessedMetrics) => {
    byYear: { [year: string]: number };
    total: string | number;
    collaborationTypes?: any;
  };
  isYearBased: boolean;
  suffix?: string;
  isCollaboration?: boolean;
}

// Security: Input validation and sanitization functions
const sanitizeFilename = (filename: string): string => {
  // Remove path traversal characters and other dangerous patterns
  return filename
    .replace(/[<>:"/\\|?*]/g, '') // Remove invalid filename characters
    .replace(/\.\./g, '') // Remove path traversal
    .replace(/^[.-]+/, '') // Remove leading dots and dashes
    .substring(0, 100); // Limit length
};

const sanitizeText = (text: string | undefined): string => {
  if (!text) return '';
  // Remove potentially dangerous characters and limit length
  return text
    .replace(/[<>]/g, '') // Remove angle brackets
    .replace(/javascript:/gi, '') // Remove javascript: protocol
    .replace(/data:/gi, '') // Remove data: protocol
    .substring(0, 500); // Limit length
};

const validateExportData = (data: ExportData[]): ExportData[] => {
  if (!Array.isArray(data)) {
    throw new Error('Invalid export data: must be an array');
  }
  
  if (data.length > 100) {
    throw new Error('Too many authors for export (max 100)');
  }
  
  return data.map(item => {
    if (!item || typeof item !== 'object') {
      throw new Error('Invalid export data item');
    }
    
    if (!item.authorId || typeof item.authorId !== 'string') {
      throw new Error('Invalid author ID');
    }
    
    // Sanitize author data
    return {
      ...item,
      authorId: sanitizeText(item.authorId),
      authorName: sanitizeText(item.authorName),
      selectedMetrics: Array.isArray(item.selectedMetrics) 
        ? item.selectedMetrics.filter(m => typeof m === 'string').slice(0, 20)
        : undefined,
      metricOrder: Array.isArray(item.metricOrder)
        ? item.metricOrder.filter(m => typeof m === 'string').slice(0, 20)
        : undefined
    };
  });
};

const metricDefinitions: MetricDefinition[] = [
  {
    id: 'publication',
    label: 'Publication',
    getData: (m) => m.scholarlyOutput,
    isYearBased: true
  },
  {
    id: 'fwci',
    label: 'FWCI',
    getData: (m) => m.fwci,
    isYearBased: true
  },
  {
    id: 'topJournal',
    label: 'Top 10 Journal %',
    getData: (m) => m.topJournal,
    isYearBased: true,
    suffix: '%'
  },
  {
    id: 'citations',
    label: 'Citations (Excl. Self-citation)',
    getData: (m) => m.citations,
    isYearBased: true
  },
  {
    id: 'citationsIncl',
    label: 'Citations (Incl. Self-citation)',
    getData: (m) => m.citationsIncl || { byYear: {}, total: 'N/A' },
    isYearBased: true
  },
  {
    id: 'hIndex',
    label: 'H-Index',
    getData: (m) => ({ byYear: {}, total: m.hIndex.value }),
    isYearBased: false
  },
  {
    id: 'collaboration',
    label: 'Collaboration (International %)',
    getData: (m) => m.collaboration || { byYear: {}, total: 'N/A' },
    isYearBased: true,
    isCollaboration: true,
    suffix: '%'
  },
  {
    id: 'academicCorporateCollaboration',
    label: 'Academic Corporate Collaboration %',
    getData: (m) => m.academicCorporateCollaboration || { byYear: {}, total: 'N/A' },
    isYearBased: true,
    isCollaboration: true,
    suffix: '%'
  }
];

const getSelectedMetrics = (data: ExportData) => {
  const selectedIds = data.selectedMetrics || metricDefinitions.map(m => m.id);
  const order = data.metricOrder || metricDefinitions.map(m => m.id);
  
  return order
    .filter(id => selectedIds.includes(id))
    .map(id => metricDefinitions.find(m => m.id === id))
    .filter((m): m is MetricDefinition => m !== undefined);
};

const getDynamicYears = (data: ExportData): string[] => {
  // Try to get years from data source first
  if (data.dataSource?.metricStartYear && data.dataSource?.metricEndYear) {
    const years = [];
    for (let year = data.dataSource.metricStartYear; year <= data.dataSource.metricEndYear; year++) {
      years.push(year.toString());
    }
    return years;
  }
  
  // Fallback: analyze actual data to determine year range
  const allYearData = [
    data.metrics.scholarlyOutput.byYear,
    data.metrics.fwci.byYear,
    data.metrics.topJournal.byYear,
    data.metrics.citations.byYear,
    data.metrics.citationsIncl?.byYear || {},
    data.metrics.collaboration?.byYear || {},
    data.metrics.academicCorporateCollaboration?.byYear || {}
  ];
  
  const allYears = new Set<number>();
  allYearData.forEach(yearData => {
    Object.keys(yearData).forEach(year => {
      const yearNum = parseInt(year);
      if (!isNaN(yearNum)) {
        allYears.add(yearNum);
      }
    });
  });
  
  if (allYears.size > 0) {
    return Array.from(allYears).sort((a, b) => a - b).map(y => y.toString());
  }
  
  // Final fallback
  return ['2019', '2020', '2021', '2022', '2023', '2024'];
};

const formatExportValue = (value: number | string, suffix: string = ''): string => {
  if (value === 'N/A' || value === undefined || value === null) return 'N/A';
  
  // Special formatting for percentages - format properly
  if (suffix === '%' && typeof value === 'number') {
    // If it's a whole number, don't show decimals
    return value % 1 === 0 ? `${Math.round(value)}${suffix}` : `${value.toFixed(2)}${suffix}`;
  }
  
  return `${value}${suffix}`;
};

const getFormattedCellValue = (yearData: { [year: string]: number }, year: string, isCollaboration: boolean = false): string => {
  const value = yearData[year];
  if (value !== undefined) {
    // Format collaboration values properly with %
    if (isCollaboration) {
      return value % 1 === 0 ? `${Math.round(value)}%` : `${value.toFixed(2)}%`;
    }
    return value.toString();
  }
  return 'N/A';
};

export const exportToPDF = (data: ExportData[], filename: string = 'research-metrics') => {
  // Security: Validate and sanitize input data
  const validatedData = validateExportData(data);
  const sanitizedFilename = sanitizeFilename(filename);
  
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.width;
  
  // Title
  doc.setFontSize(20);
  doc.setTextColor(40, 40, 40);
  doc.text('SciVal Research Metrics Report', pageWidth / 2, 20, { align: 'center' });
  
  // Date
  doc.setFontSize(10);
  doc.setTextColor(100, 100, 100);
  doc.text(`Generated on: ${new Date().toLocaleDateString()}`, pageWidth / 2, 30, { align: 'center' });
  
  let yPosition = 45;
  
  validatedData.forEach((authorData, index) => {
    // Check if we need a new page
    if (yPosition > 250) {
      doc.addPage();
      yPosition = 20;
    }
    
    // Author header with name if available
    doc.setFontSize(14);
    doc.setTextColor(40, 40, 40);
    const authorTitle = authorData.authorName 
      ? `${sanitizeText(authorData.authorName)} (ID: ${sanitizeText(authorData.authorId)})`
      : `Author ID: ${sanitizeText(authorData.authorId)}`;
    doc.text(authorTitle, 20, yPosition);
    yPosition += 10;
    
    // Data source info
    if (authorData.dataSource) {
      doc.setFontSize(9);
      doc.setTextColor(80, 80, 80);
      doc.text(`Source: ${authorData.dataSource.sourceName} | Last Updated: ${authorData.dataSource.lastUpdated}`, 20, yPosition);
      yPosition += 8;
    }
    
    // Get selected metrics and dynamic years for this author
    const selectedMetrics = getSelectedMetrics(authorData);
    const years = getDynamicYears(authorData);
    
    if (selectedMetrics.length === 0) {
      doc.setFontSize(10);
      doc.setTextColor(150, 150, 150);
      doc.text('No metrics selected for export', 20, yPosition);
      yPosition += 15;
    } else {
      // Prepare table data
      const tableData = selectedMetrics.map(metric => {
        const data = metric.getData(authorData.metrics);
        const isCollaboration = metric.isCollaboration;
        
        if (metric.isYearBased) {
          return [
            metric.label,
            ...years.map(year => getFormattedCellValue(data.byYear, year, isCollaboration)),
            formatExportValue(data.total, metric.suffix || '')
          ];
        } else {
          return [
            metric.label,
            ...years.map(() => 'N/A'),
            formatExportValue(data.total, metric.suffix || '')
          ];
        }
      });
      
      // Create table
      autoTable(doc, {
        startY: yPosition,
        head: [['Metric', ...years, 'Total']],
        body: tableData,
        theme: 'grid',
        headStyles: {
          fillColor: [59, 130, 246],
          textColor: 255,
          fontSize: 9,
          fontStyle: 'bold'
        },
        bodyStyles: {
          fontSize: 8,
          textColor: 60
        },
        alternateRowStyles: {
          fillColor: [248, 250, 252]
        },
        columnStyles: {
          0: { fontStyle: 'bold', fillColor: [243, 244, 246] }
        },
        margin: { left: 20, right: 20 }
      });
      
      yPosition = (doc as any).lastAutoTable.finalY + 20;

      // Add collaboration breakdown if selected
      const collaborationMetric = selectedMetrics.find(m => m.id === 'collaboration');
      if (collaborationMetric && authorData.metrics.collaboration?.collaborationTypes) {
        const collabTypes = authorData.metrics.collaboration.collaborationTypes;
        
        // Check if we need a new page
        if (yPosition > 220) {
          doc.addPage();
          yPosition = 20;
        }
        
        doc.setFontSize(12);
        doc.setTextColor(40, 40, 40);
        doc.text('Collaboration Breakdown', 20, yPosition);
        yPosition += 10;
        
        const collabTableData = Object.entries(collabTypes).map(([type, data]: [string, any]) => [
          type.replace(/([A-Z])/g, ' $1').trim(),
          formatExportValue(data.total, '%')
        ]);
        
        autoTable(doc, {
          startY: yPosition,
          head: [['Collaboration Type', 'Average %']],
          body: collabTableData,
          theme: 'grid',
          headStyles: {
            fillColor: [147, 51, 234],
            textColor: 255,
            fontSize: 9,
            fontStyle: 'bold'
          },
          bodyStyles: {
            fontSize: 8,
            textColor: 60
          },
          margin: { left: 20, right: 20 }
        });
        
        yPosition = (doc as any).lastAutoTable.finalY + 20;
      }

      // Add academic corporate collaboration breakdown if selected
      const academicCorporateMetric = selectedMetrics.find(m => m.id === 'academicCorporateCollaboration');
      if (academicCorporateMetric && authorData.metrics.academicCorporateCollaboration?.collaborationTypes) {
        const collabTypes = authorData.metrics.academicCorporateCollaboration.collaborationTypes;
        
        // Check if we need a new page
        if (yPosition > 220) {
          doc.addPage();
          yPosition = 20;
        }
        
        doc.setFontSize(12);
        doc.setTextColor(40, 40, 40);
        doc.text('Academic Corporate Collaboration Breakdown', 20, yPosition);
        yPosition += 10;
        
        const collabTableData = Object.entries(collabTypes).map(([type, data]: [string, any]) => [
          type.replace(/([A-Z])/g, ' $1').trim(),
          formatExportValue(data.total, '%')
        ]);
        
        autoTable(doc, {
          startY: yPosition,
          head: [['Collaboration Type', 'Average %']],
          body: collabTableData,
          theme: 'grid',
          headStyles: {
            fillColor: [16, 185, 129],
            textColor: 255,
            fontSize: 9,
            fontStyle: 'bold'
          },
          bodyStyles: {
            fontSize: 8,
            textColor: 60
          },
          margin: { left: 20, right: 20 }
        });
        
        yPosition = (doc as any).lastAutoTable.finalY + 20;
      }
    }
    
    // Add separator between authors if there are multiple
    if (index < validatedData.length - 1) {
      doc.setDrawColor(200, 200, 200);
      doc.line(20, yPosition - 10, pageWidth - 20, yPosition - 10);
    }
  });
  
  // Save the PDF
  doc.save(`${sanitizedFilename}.pdf`);
};

export const exportToExcel = (data: ExportData[], filename: string = 'research-metrics') => {
  // Security: Validate and sanitize input data
  const validatedData = validateExportData(data);
  const sanitizedFilename = sanitizeFilename(filename);
  
  const workbook = XLSX.utils.book_new();
  
  validatedData.forEach((authorData, index) => {
    const years = getDynamicYears(authorData);
    
    // Create worksheet data
    const worksheetData = [
      ['SciVal Research Metrics Report'],
      [authorData.authorName 
        ? `Author: ${sanitizeText(authorData.authorName)} (ID: ${sanitizeText(authorData.authorId)})`
        : `Author ID: ${sanitizeText(authorData.authorId)}`
      ],
      [`Generated on: ${new Date().toLocaleDateString()}`],
      [],
    ];
    
    // Add data source info
    if (authorData.dataSource) {
      worksheetData.push([`Source: ${authorData.dataSource.sourceName}`]);
      worksheetData.push([`Last Updated: ${authorData.dataSource.lastUpdated}`]);
      worksheetData.push([`Period: ${authorData.dataSource.metricStartYear} - ${authorData.dataSource.metricEndYear}`]);
      worksheetData.push([]);
    }
    
    // Get selected metrics for this author
    const selectedMetrics = getSelectedMetrics(authorData);
    
    if (selectedMetrics.length === 0) {
      worksheetData.push(['No metrics selected for export']);
    } else {
      // Add table headers
      worksheetData.push(['Metric', ...years, 'Total']);
      
      // Add metrics data
      selectedMetrics.forEach(metric => {
        const data = metric.getData(authorData.metrics);
        const isCollaboration = metric.isCollaboration;
        
        if (metric.isYearBased) {
          worksheetData.push([
            metric.label,
            ...years.map(year => {
              const value = data.byYear[year];
              if (value !== undefined) {
                return isCollaboration ? (value % 1 === 0 ? Math.round(value) : parseFloat(value.toFixed(2))) : value;
              }
              return 'N/A';
            }),
            typeof data.total === 'number' && isCollaboration ? (data.total % 1 === 0 ? Math.round(data.total) : parseFloat(data.total.toFixed(2))) : data.total
          ]);
        } else {
          worksheetData.push([
            metric.label,
            ...years.map(() => 'N/A'),
            data.total
          ]);
        }
      });

      // Add collaboration breakdown if selected
      const collaborationMetric = selectedMetrics.find(m => m.id === 'collaboration');
      if (collaborationMetric && authorData.metrics.collaboration?.collaborationTypes) {
        worksheetData.push([]);
        worksheetData.push(['Collaboration Breakdown']);
        worksheetData.push(['Collaboration Type', 'Average %']);
        
        Object.entries(authorData.metrics.collaboration.collaborationTypes).forEach(([type, data]: [string, any]) => {
          worksheetData.push([
            type.replace(/([A-Z])/g, ' $1').trim(),
            typeof data.total === 'number' ? (data.total % 1 === 0 ? Math.round(data.total) : parseFloat(data.total.toFixed(2))) : data.total
          ]);
        });
      }

      // Add academic corporate collaboration breakdown if selected
      const academicCorporateMetric = selectedMetrics.find(m => m.id === 'academicCorporateCollaboration');
      if (academicCorporateMetric && authorData.metrics.academicCorporateCollaboration?.collaborationTypes) {
        worksheetData.push([]);
        worksheetData.push(['Academic Corporate Collaboration Breakdown']);
        worksheetData.push(['Collaboration Type', 'Average %']);
        
        Object.entries(authorData.metrics.academicCorporateCollaboration.collaborationTypes).forEach(([type, data]: [string, any]) => {
          worksheetData.push([
            type.replace(/([A-Z])/g, ' $1').trim(),
            typeof data.total === 'number' ? (data.total % 1 === 0 ? Math.round(data.total) : parseFloat(data.total.toFixed(2))) : data.total
          ]);
        });
      }
    }
    
    // Create worksheet
    const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
    
    // Style the worksheet
    const range = XLSX.utils.decode_range(worksheet['!ref'] || 'A1');
    
    // Set column widths
    worksheet['!cols'] = [
      { width: 25 }, // Metric column
      ...years.map(() => ({ width: 12 })), // Year columns
      { width: 15 } // Total column
    ];
    
    // Add worksheet to workbook
    const sheetName = data.length > 1 ? `Author_${index + 1}` : 'Metrics';
    XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
  });
  
  // Save the Excel file
  XLSX.writeFile(workbook, `${sanitizedFilename}.xlsx`);
};