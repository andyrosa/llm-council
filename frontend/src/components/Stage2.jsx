import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { convertLatexDelimiters } from '../utils/latex';
import { formatStats } from '../utils/stats';
import { generateStatsGraph } from '../utils/graph';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  // Replace each "Response X" with the actual model name
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings, progress }) {
  const [activeTab, setActiveTab] = useState(0);

  const costBaseline = aggregateRankings && aggregateRankings.length > 0
    ? Math.min(...aggregateRankings.map((agg) => (agg.total_cost ?? Infinity)))
    : Infinity;

  const timeBaseline = aggregateRankings && aggregateRankings.length > 0
    ? Math.min(...aggregateRankings.map((agg) => (agg.total_elapsed_time ?? Infinity)))
    : Infinity;

  const computeColor = (value, baseline) => {
    if (value === null || value === undefined || !isFinite(value)) return '';
    if (!isFinite(baseline)) return '';

    // If baseline is zero, keep zero as green and use first non-zero as thresholds
    if (baseline === 0) {
      const nonZero = aggregateRankings
        ?.map((agg) => valueKeySelector(agg, baseline === costBaseline ? 'total_cost' : 'total_elapsed_time'))
        ?.filter((v) => v !== null && v !== undefined && isFinite(v) && v > 0);
      const firstNonZero = nonZero && nonZero.length > 0 ? Math.min(...nonZero) : null;
      if (value === 0) return 'green';
      if (firstNonZero === null) return 'green';
      const t1 = firstNonZero * 1.2;
      const t2 = firstNonZero * 1.4;
      if (value <= t1) return 'yellow';
      if (value <= t2) return 'red';
      return 'red';
    }

    const t1 = baseline * 1.2;
    const t2 = baseline * 1.4;
    if (value <= t1) return 'green';
    if (value <= t2) return 'yellow';
    return 'red';
  };

  // Selector helper used for zero-baseline logic
  const valueKeySelector = (agg, key) => {
    if (!agg) return undefined;
    return agg[key];
  };

  if (!rankings || rankings.length === 0) {
    return null;
  }

  const activeRanking = rankings[activeTab];
  const stats = formatStats(activeRanking.elapsed_time, activeRanking.cost);
  const showProgress = progress && progress.total > 0 && progress.completed < progress.total;

  return (
    <div className="stage stage2">
      <h3 className="stage-title">
        Stage 2: Peer Rankings
        {showProgress && (
          <span className="stage-progress">
            ({progress.completed}/{progress.total} judges)
          </span>
        )}
      </h3>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each model evaluated all responses (anonymized as Response A, B, C, etc.) and provided rankings.
        Below, model names are shown in <strong>bold</strong> for readability, but the original evaluation used anonymous labels.
      </p>

      <div className="tabs">
        {rankings.map((rank, index) => (
          <button
            type="button"
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {rank.model.split('/')[1] || rank.model}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-header">
          <span className="ranking-model">{activeRanking.model}</span>
          {stats && <span className="model-stats-inline">{stats}</span>}
        </div>
        <div className="ranking-content markdown-content">
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
            {convertLatexDelimiters(deAnonymizeText(activeRanking.ranking, labelToModel))}
          </ReactMarkdown>
        </div>

        {activeRanking.parsed_ranking &&
         activeRanking.parsed_ranking.length > 0 && (
          <div className="parsed-ranking">
            <strong>Extracted Ranking:</strong>
            <ol>
              {activeRanking.parsed_ranking.map((label, i) => (
                <li key={i}>
                  {labelToModel && labelToModel[label]
                    ? labelToModel[label].split('/')[1] || labelToModel[label]
                    : label}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Aggregate Rankings (Street Cred)</h4>
          <p className="stage-description">
            Combined results across all peer evaluations (lower score is better):
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => (
              <div key={index} className="aggregate-item">
                <span className="rank-position">#{index + 1}</span>
                <span className="rank-model">
                  {agg.model.split('/')[1] || agg.model}
                </span>
                <span className="rank-score">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="rank-count">
                  ({agg.rankings_count} votes)
                </span>
                {(agg.total_elapsed_time !== undefined || agg.total_cost !== undefined) && (
                  <span className="rank-stats">
                    {agg.total_elapsed_time !== undefined && agg.total_elapsed_time !== null && (
                      <span className="rank-stat">
                        <span className={`stat-dot stat-${computeColor(agg.total_elapsed_time, timeBaseline)}`} />
                        <span className="stat-text">{`${agg.total_elapsed_time}s`}</span>
                      </span>
                    )}
                    {agg.total_elapsed_time !== undefined && agg.total_elapsed_time !== null && agg.total_cost !== undefined && agg.total_cost !== null && (
                      <span className="rank-stat-divider">·</span>
                    )}
                    {agg.total_cost !== undefined && agg.total_cost !== null && (
                      <span className="rank-stat">
                        <span className={`stat-dot stat-${computeColor(agg.total_cost, costBaseline)}`} />
                        <span className="stat-text">{`$${agg.total_cost.toFixed(2)}`}</span>
                      </span>
                    )}
                  </span>
                )}
              </div>
            ))}
          </div>
          <div className="aggregate-graph">
            <img 
              src={generateStatsGraph(aggregateRankings)} 
              alt="Performance Graph" 
              style={{maxWidth: '100%', marginTop: '20px', border: '1px solid #eee', borderRadius: '4px'}} 
            />
          </div>
        </div>
      )}
    </div>
  );
}
