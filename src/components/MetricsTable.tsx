import React, { useState, useEffect } from 'react';
import { ProcessedMetrics } from '../types';
import { GripVertical, Check } from 'lucide-react';

interface MetricOption {
  id: string;
  label: string;
  description: string;
  enabled: boolean;
}

interface MetricsTableProps {
  metrics: ProcessedMetrics;
  dataSource?: {
    metricStartYear: number;
    metricEndYear: number;
  };
  availableMetrics: MetricOption[];
  onSelectionChange?: (selectedMetrics: string[], metricOrder: string[]) => void;
}

interface MetricRow {
  id: string;
  label: string;
  getData: (metrics: ProcessedMetrics) => {
    byYear: { [year: string]: number };
    total: string | number;
    collaborationTypes?: any;
  };
  isYearBased: boolean;
  isCollaboration?: boolean;
}

const MetricsTable: React.FC<MetricsTableProps> = ({ metrics, dataSource, availableMetrics, onSelectionChange }) => {
  // Generate dynamic years based on data source or fallback to default range
  const generateYears = () => {
    if (dataSource?.metricStartYear && dataSource?.metricEndYear) {
      const years = [];
      for (let year = dataSource.metricStartYear; year <= dataSource.metricEndYear; year++) {
        years.push(year);
      }
      return years;
    }
    
    // Fallback: analyze actual data to determine year range
    const allYearData = [
      metrics.scholarlyOutput.byYear,
      metrics.fwci.byYear,
      metrics.topJournal.byYear,
      metrics.citationCount.byYear,
      metrics.citationsPerPublication.byYear,
      metrics.collaboration?.byYear || {},
      metrics.academicCorporateCollaboration?.byYear || {}
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
      return Array.from(allYears).sort((a, b) => a - b);
    }
    
    // Final fallback
    return [2019, 2020, 2021, 2022, 2023, 2024];
  };

  const years = generateYears();
  
  const defaultMetrics: MetricRow[] = [
    {
      id: 'publication',
      label: 'Publication',
      getData: (m) => m.scholarlyOutput,
      isYearBased: true
    },
    {
      id: 'citationCount',
      label: 'Citation Count',
      getData: (m) => m.citationCount,
      isYearBased: true
    },
    {
      id: 'citationsPerPublication',
      label: 'Citations Per Publication',
      getData: (m) => m.citationsPerPublication,
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
      isCollaboration: true
    },
    {
      id: 'academicCorporateCollaboration',
      label: 'Academic Corporate Collaboration %',
      getData: (m) => m.academicCorporateCollaboration || { byYear: {}, total: 'N/A' },
      isYearBased: true,
      isCollaboration: true
    }
  ];

  // Filter metrics based on what's enabled in the parent component
  const enabledMetricIds = availableMetrics.filter(m => m.enabled).map(m => m.id);
  
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(enabledMetricIds);
  const [metricOrder, setMetricOrder] = useState<string[]>(enabledMetricIds);
  const [draggedItem, setDraggedItem] = useState<string | null>(null);

  // Update selected metrics when availableMetrics changes
  useEffect(() => {
    const newEnabledIds = availableMetrics.filter(m => m.enabled).map(m => m.id);
    setSelectedMetrics(newEnabledIds);
    setMetricOrder(prev => {
      // Maintain order but filter out disabled metrics and add new ones
      const filteredOrder = prev.filter(id => newEnabledIds.includes(id));
      const newMetrics = newEnabledIds.filter(id => !filteredOrder.includes(id));
      return [...filteredOrder, ...newMetrics];
    });
  }, [availableMetrics]);

  // Notify parent component of changes
  useEffect(() => {
    if (onSelectionChange) {
      onSelectionChange(selectedMetrics, metricOrder);
    }
  }, [selectedMetrics, metricOrder, onSelectionChange]);

  const formatValue = (value: number | string, suffix: string = ''): string => {
    if (value === 'N/A' || value === undefined || value === null) return 'N/A';
    
    // Special formatting for percentages - format properly
    if (suffix === '%' && typeof value === 'number') {
      // If it's a whole number, don't show decimals
      return value % 1 === 0 ? `${Math.round(value)}${suffix}` : `${value.toFixed(2)}${suffix}`;
    }
    
    return `${value}${suffix}`;
  };

  const getCellValue = (yearData: { [year: string]: number }, year: number, isTopJournal: boolean = false, isCollaboration: boolean = false): string => {
    const value = yearData[year.toString()];
    if (value !== undefined) {
      // Format Top Journal % and Collaboration % values properly
      if (isTopJournal || isCollaboration) {
        return value % 1 === 0 ? `${Math.round(value)}%` : `${value.toFixed(2)}%`;
      }
      return value.toString();
    }
    return 'N/A';
  };

  const handleMetricToggle = (metricId: string) => {
    setSelectedMetrics(prev => 
      prev.includes(metricId) 
        ? prev.filter(id => id !== metricId)
        : [...prev, metricId]
    );
  };

  const handleDragStart = (e: React.DragEvent, metricId: string) => {
    setDraggedItem(metricId);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent, targetId: string) => {
    e.preventDefault();
    
    if (!draggedItem || draggedItem === targetId) {
      setDraggedItem(null);
      return;
    }

    const newOrder = [...metricOrder];
    const draggedIndex = newOrder.indexOf(draggedItem);
    const targetIndex = newOrder.indexOf(targetId);

    // Remove dragged item and insert at target position
    newOrder.splice(draggedIndex, 1);
    newOrder.splice(targetIndex, 0, draggedItem);

    setMetricOrder(newOrder);
    setDraggedItem(null);
  };

  const handleDragEnd = () => {
    setDraggedItem(null);
  };

  // Get ordered metrics based on current order and filter by what's available
  const orderedMetrics = metricOrder
    .filter(id => enabledMetricIds.includes(id)) // Only show metrics that are enabled
    .map(id => defaultMetrics.find(m => m.id === id))
    .filter((m): m is MetricRow => m !== undefined);

  return (
    <div className="space-y-4">
      {/* Year Range Info */}
      {years.length > 0 && (
        <div className="bg-gradient-to-r from-slate-50 to-blue-50 rounded-lg p-3 border border-slate-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <span className="text-sm font-medium text-slate-700">Data Period:</span>
              <span className="text-sm text-slate-600">{years[0]} - {years[years.length - 1]}</span>
              <span className="text-xs text-slate-500">({years.length} years)</span>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => setSelectedMetrics(enabledMetricIds)}
                className="px-3 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors duration-200"
              >
                Select All Available
              </button>
              <button
                onClick={() => setSelectedMetrics([])}
                className="px-3 py-1 text-xs bg-gray-600 text-white rounded-md hover:bg-gray-700 transition-colors duration-200"
              >
                Clear All
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Metrics Table */}
      <div className="overflow-x-auto shadow-lg rounded-lg border border-gray-200">
        <table className="w-full bg-white">
          <thead>
            <tr className="bg-gradient-to-r from-blue-50 to-indigo-50">
              <th className="px-3 py-4 text-center text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200 w-12">
                ✓
              </th>
              <th className="px-2 py-4 text-center text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200 w-8">
                ⋮⋮
              </th>
              <th className="px-6 py-4 text-left text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200">
                Metric
              </th>
              {years.map(year => (
                <th key={year} className="px-4 py-4 text-center text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200">
                  {year}
                </th>
              ))}
              <th className="px-6 py-4 text-center text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200">
                Total
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {orderedMetrics.map((metric) => {
              const data = metric.getData(metrics);
              const isSelected = selectedMetrics.includes(metric.id);
              const isDragging = draggedItem === metric.id;
              const isTopJournal = metric.id === 'topJournal';
              const isCollaboration = metric.isCollaboration;
              
              return (
                <tr 
                  key={metric.id} 
                  className={`transition-all duration-200 ${
                    isDragging 
                      ? 'bg-blue-100 shadow-lg transform scale-105' 
                      : isSelected 
                        ? 'hover:bg-gray-50' 
                        : 'hover:bg-gray-50 opacity-60'
                  }`}
                  draggable
                  onDragStart={(e) => handleDragStart(e, metric.id)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDrop(e, metric.id)}
                  onDragEnd={handleDragEnd}
                >
                  {/* Selection Checkbox */}
                  <td className="px-3 py-4 text-center">
                    <button
                      onClick={() => handleMetricToggle(metric.id)}
                      className={`flex items-center justify-center w-5 h-5 rounded border-2 transition-all duration-200 ${
                        isSelected
                          ? 'bg-blue-600 border-blue-600 text-white'
                          : 'border-gray-300 hover:border-blue-400'
                      }`}
                    >
                      {isSelected && <Check className="h-3 w-3" />}
                    </button>
                  </td>
                  
                  {/* Drag Handle */}
                  <td className="px-2 py-4 text-center cursor-move">
                    <GripVertical className="h-4 w-4 text-gray-400 hover:text-gray-600 transition-colors duration-200" />
                  </td>
                  
                  {/* Metric Name */}
                  <td className={`px-6 py-4 text-sm font-medium ${
                    isSelected ? 'text-gray-900' : 'text-gray-400'
                  }`}>
                    {metric.label}
                  </td>
                  
                  {/* Year Data or N/A for non-year-based metrics */}
                  {metric.isYearBased ? (
                    years.map(year => (
                      <td key={year} className={`px-4 py-4 text-sm text-center ${
                        isSelected ? 'text-gray-700' : 'text-gray-400'
                      }`}>
                        {getCellValue(data.byYear, year, isTopJournal, isCollaboration)}
                      </td>
                    ))
                  ) : (
                    <td colSpan={years.length} className={`px-4 py-4 text-sm text-center italic ${
                      isSelected ? 'text-gray-500' : 'text-gray-400'
                    }`}>
                      Cumulative metric - not calculated by year
                    </td>
                  )}
                  
                  {/* Total */}
                  <td className={`px-6 py-4 text-sm font-semibold text-center ${
                    isSelected ? 'text-gray-900' : 'text-gray-400'
                  } ${
                    metric.id === 'hIndex' ? 'bg-indigo-100' : 'bg-blue-50'
                  }`}>
                    {isTopJournal || isCollaboration
                      ? formatValue(data.total, '%')
                      : formatValue(data.total)
                    }
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Collaboration Details */}
      {selectedMetrics.includes('collaboration') && metrics.collaboration?.collaborationTypes && (
        <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg p-6 border border-purple-200">
          <h4 className="text-lg font-semibold text-purple-900 mb-4">Collaboration Breakdown</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(metrics.collaboration.collaborationTypes).map(([type, data]: [string, any]) => {
              // Get all available years from the collaboration data
              const availableYears = Object.keys(data.byYear).sort();
              
              return (
                <div key={type} className="bg-white rounded-lg p-4 border border-purple-200">
                  <h5 className="text-sm font-medium text-purple-800 mb-2 capitalize">
                    {type.replace(/([A-Z])/g, ' $1').trim()}
                  </h5>
                  <div className="space-y-1">
                    <div className="text-xs text-purple-600">
                      Average: <span className="font-semibold">{formatValue(data.total, '%')}</span>
                    </div>
                    {/* Show all available years, not just the first 3 */}
                    {availableYears.map((year: string) => (
                      <div key={year} className="text-xs text-purple-600">
                        {year}: {formatValue(data.byYear[year], '%')}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Academic Corporate Collaboration Details */}
      {selectedMetrics.includes('academicCorporateCollaboration') && metrics.academicCorporateCollaboration?.collaborationTypes && (
        <div className="bg-gradient-to-r from-emerald-50 to-green-50 rounded-lg p-6 border border-emerald-200">
          <h4 className="text-lg font-semibold text-emerald-900 mb-4">Academic Corporate Collaboration Breakdown</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(metrics.academicCorporateCollaboration.collaborationTypes).map(([type, data]: [string, any]) => {
              // Get all available years from the collaboration data
              const availableYears = Object.keys(data.byYear).sort();
              
              return (
                <div key={type} className="bg-white rounded-lg p-4 border border-emerald-200">
                  <h5 className="text-sm font-medium text-emerald-800 mb-2 capitalize">
                    {type.replace(/([A-Z])/g, ' $1').trim()}
                  </h5>
                  <div className="space-y-1">
                    <div className="text-xs text-emerald-600">
                      Average: <span className="font-semibold">{formatValue(data.total, '%')}</span>
                    </div>
                    {/* Show all available years */}
                    {availableYears.map((year: string) => (
                      <div key={year} className="text-xs text-emerald-600">
                        {year}: {formatValue(data.byYear[year], '%')}
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {selectedMetrics.length === 0 && (
        <div className="text-center py-8 bg-gray-50 rounded-lg border border-gray-200">
          <p className="text-gray-500">No metrics selected. Please select at least one metric to display and export.</p>
        </div>
      )}
      
      {selectedMetrics.length > 0 && (
        <div className="text-center py-2">
          <p className="text-sm text-gray-600">
            {selectedMetrics.length} of {enabledMetricIds.length} available metrics selected for export
          </p>
        </div>
      )}
    </div>
  );
};

export default MetricsTable;