import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { convertLatexDelimiters } from '../utils/latex';
import { formatStats } from '../utils/stats';
import './Stage1.css';

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  const activeResponse = responses[activeTab];
  const stats = formatStats(activeResponse.elapsed_time, activeResponse.cost);

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div className="tabs">
        {responses.map((resp, index) => (
          <button
            type="button"
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {resp.model.split('/')[1] || resp.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-header">
          <span className="model-name">{activeResponse.model}</span>
          {stats && <span className="model-stats-inline">{stats}</span>}
        </div>
        <div className="response-text markdown-content">
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
            {convertLatexDelimiters(activeResponse.response)}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
