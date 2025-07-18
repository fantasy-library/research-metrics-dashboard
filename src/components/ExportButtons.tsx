import React, { useState, useRef } from 'react';
import { Download } from 'lucide-react';
import { exportToPDF, exportToExcel, ExportData } from '../utils/exportUtils';

interface ExportButtonsProps {
  data: ExportData[];
  disabled?: boolean;
  onExport?: (format: 'pdf' | 'excel') => void;
}

export const ExportButtons: React.FC<ExportButtonsProps> = ({ data, disabled = false, onExport }) => {
  const [isExporting, setIsExporting] = useState(false);
  const lastExportTime = useRef<number>(0);
  
  // Rate limiting: prevent exports more frequently than every 2 seconds
  const RATE_LIMIT_MS = 2000;
  
  const handleExport = async (format: 'pdf' | 'excel', exportFunction: (data: ExportData[], filename: string) => void) => {
    if (data.length === 0) return;
    
    // Check rate limiting
    const now = Date.now();
    if (now - lastExportTime.current < RATE_LIMIT_MS) {
      alert('Please wait a moment before exporting again.');
      return;
    }
    
    try {
      setIsExporting(true);
      lastExportTime.current = now;
      
      const filename = data.length === 1 
        ? `research-metrics-${data[0].authorId}`
        : `research-metrics-${data.length}-authors`;
      
      // Security: Validate data before export
      if (data.length > 100) {
        throw new Error('Too many authors for export (maximum 100)');
      }
      
      exportFunction(data, filename);
      onExport?.(format);
      
    } catch (error) {
      console.error('Export error:', error);
      alert(`Export failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    } finally {
      setIsExporting(false);
    }
  };

  const handlePDFExport = () => {
    handleExport('pdf', exportToPDF);
  };

  const handleExcelExport = () => {
    handleExport('excel', exportToExcel);
  };

  if (disabled || data.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col sm:flex-row gap-3 mb-6">
      <button
        onClick={handlePDFExport}
        disabled={isExporting}
        className="flex items-center justify-center space-x-3 px-4 py-3 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-xl font-medium hover:from-red-600 hover:to-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <i className="fa fa-file-pdf-o" style={{ fontSize: '20px', color: 'white' }}></i>
        <span>{isExporting ? 'Exporting...' : 'Export as PDF'}</span>
        <Download className="h-4 w-4" />
      </button>
      
      <button
        onClick={handleExcelExport}
        disabled={isExporting}
        className="flex items-center justify-center space-x-3 px-4 py-3 bg-gradient-to-r from-green-500 to-green-600 text-white rounded-xl font-medium hover:from-green-600 hover:to-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <i className="fa fa-file-excel-o" style={{ fontSize: '20px', color: 'white' }}></i>
        <span>{isExporting ? 'Exporting...' : 'Export as Excel'}</span>
        <Download className="h-4 w-4" />
      </button>
    </div>
  );
};