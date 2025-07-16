import React from 'react';
import { Download, FileText, Table } from 'lucide-react';
import { exportToPDF, exportToExcel, ExportData } from '../utils/exportUtils';

interface ExportButtonsProps {
  data: ExportData[];
  disabled?: boolean;
  onExport?: (format: 'pdf' | 'excel') => void;
}

export const ExportButtons: React.FC<ExportButtonsProps> = ({ data, disabled = false, onExport }) => {
  const handlePDFExport = () => {
    if (data.length === 0) return;
    
    const filename = data.length === 1 
      ? `research-metrics-${data[0].authorId}`
      : `research-metrics-${data.length}-authors`;
    
    exportToPDF(data, filename);
    onExport?.('pdf');
  };

  const handleExcelExport = () => {
    if (data.length === 0) return;
    
    const filename = data.length === 1 
      ? `research-metrics-${data[0].authorId}`
      : `research-metrics-${data.length}-authors`;
    
    exportToExcel(data, filename);
    onExport?.('excel');
  };

  if (disabled || data.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-col sm:flex-row gap-3 mb-6">
      <button
        onClick={handlePDFExport}
        className="flex items-center justify-center space-x-2 px-4 py-3 bg-gradient-to-r from-red-500 to-red-600 text-white rounded-xl font-medium hover:from-red-600 hover:to-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-all duration-200 shadow-lg hover:shadow-xl"
      >
        <FileText className="h-4 w-4" />
        <span>Export as PDF</span>
        <Download className="h-4 w-4" />
      </button>
      
      <button
        onClick={handleExcelExport}
        className="flex items-center justify-center space-x-2 px-4 py-3 bg-gradient-to-r from-green-500 to-green-600 text-white rounded-xl font-medium hover:from-green-600 hover:to-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 transition-all duration-200 shadow-lg hover:shadow-xl"
      >
        <Table className="h-4 w-4" />
        <span>Export as Excel</span>
        <Download className="h-4 w-4" />
      </button>
    </div>
  );
};