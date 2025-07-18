import React from 'react';
import { Database, Calendar, Info } from 'lucide-react';
import { DataSource } from '../types';

interface DataSourceInfoProps {
  dataSource: DataSource;
}

export const DataSourceInfo: React.FC<DataSourceInfoProps> = ({ dataSource }) => {
  return (
    <div className="bg-gradient-to-r from-gray-50 to-blue-50 rounded-lg p-6 mb-6 border border-gray-200">
      <div className="flex items-center mb-4">
        <Info className="h-5 w-5 text-blue-600 mr-2" />
        <h3 className="text-lg font-semibold text-gray-900">Data Source Information</h3>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="flex items-center space-x-3">
          <Database className="h-4 w-4 text-gray-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Source</p>
            <p className="text-sm text-gray-600">{dataSource.sourceName}</p>
          </div>
        </div>
        
        <div className="flex items-center space-x-3">
          <Calendar className="h-4 w-4 text-gray-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Last Updated</p>
            <p className="text-sm text-gray-600">{dataSource.lastUpdated}</p>
          </div>
        </div>
        
        <div className="flex items-center space-x-3">
          <Calendar className="h-4 w-4 text-gray-600" />
          <div>
            <p className="text-sm font-medium text-gray-900">Period</p>
            <p className="text-sm text-gray-600">
              {dataSource.metricStartYear} - {dataSource.metricEndYear}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};