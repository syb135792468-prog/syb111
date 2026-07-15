import React, { useState } from 'react'
import DailyChallengeView from './DailyChallengeView'
import FreePracticePanel from '../components/FreePracticePanel'

const CodePlaygroundView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'daily' | 'free'>('daily')

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-100 bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-800">每日编程</h1>
            <p className="text-xs text-gray-400 mt-0.5">在沙箱中安全运行 Python 代码 · Ctrl+Enter 运行</p>
          </div>
          <div className="flex items-center gap-1.5 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setActiveTab('daily')}
              className={`px-5 py-2 text-sm font-semibold rounded-md transition-all ${
                activeTab === 'daily'
                  ? 'bg-white text-green-600 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              每日一题
            </button>
            <button
              onClick={() => setActiveTab('free')}
              className={`px-5 py-2 text-sm font-semibold rounded-md transition-all ${
                activeTab === 'free'
                  ? 'bg-white text-green-600 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              自由练习
            </button>
          </div>
        </div>
      </div>

      {activeTab === 'daily' ? <DailyChallengeView /> : <FreePracticePanel />}
    </div>
  )
}

export default CodePlaygroundView
