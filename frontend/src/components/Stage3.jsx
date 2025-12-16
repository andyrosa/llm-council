import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { convertLatexDelimiters } from '../utils/latex';
import { formatStats } from '../utils/stats';
import { generateStatsGraph } from '../utils/graph';
import './Stage3.css';

export default function Stage3({ finalResponse, stage1, stage2, aggregateRankings, conversationTitle, elapsedRunningTime, totalCost, webSearch, quickMode, codingMode }) {
  if (!finalResponse) {
    return null;
  }

  const stats = formatStats(finalResponse.elapsed_time, finalResponse.cost);
  
  // Calculate total cost if not provided
  const calculatedTotalCost = totalCost !== undefined ? totalCost : 
    (stage1 && stage2 ? 
      stage1.reduce((sum, r) => sum + (r.cost || 0), 0) + 
      stage2.reduce((sum, r) => sum + (r.cost || 0), 0) : 
      0);
  
  const totalStats = formatStats(elapsedRunningTime, calculatedTotalCost);

  // Helper function to increase all markdown heading levels by 1
  const increaseHeadingLevels = (markdown) => {
    return markdown.replace(/^(#{1,5}) /gm, '#$1 ');
  };

  const handleExport = () => {
    // Create filename from conversation title, or use default
    const sanitizeFilename = (name) => {
      return name
        .replace(/[<>:"\/\\|?*]/g, '') // Remove invalid filename characters
        .replace(/\s+/g, '_') // Replace spaces with underscores
        .substring(0, 100); // Limit length
    };
    const filename = conversationTitle 
      ? `${sanitizeFilename(conversationTitle)}.md`
      : 'council_report.md';
    let md = `# Final Council Answer\n\n`;
    md += `**Chairman:** ${finalResponse.model}\n`;
    md += `**Stats:** ${stats || 'N/A'}\n\n`;
    if (totalStats) {
      md += `**Elapsed running time and total cost:** ${totalStats}\n\n`;
    }
    md += `${finalResponse.response}\n\n`;

    if (aggregateRankings && stage1 && stage2) {
      // Generate graph
      try {
        const graphBase64 = generateStatsGraph(aggregateRankings, stage1);
        md += `\n# Performance Analysis\n\n`;
        md += `![Performance Graph](${graphBase64})\n\n`;
      } catch (e) {
        console.error("Failed to generate graph", e);
      }

      md += `---\n\n# Individual Model Responses\n\n`;

      // Sort rankings just in case
      const sortedRankings = [...aggregateRankings].sort((a, b) => a.average_rank - b.average_rank);

      sortedRankings.forEach((rankInfo, index) => {
        const modelName = rankInfo.model;
        const s1 = stage1.find(r => r.model === modelName);
        const s2 = stage2.find(r => r.model === modelName);

        md += `## ${index + 1}. ${modelName}\n\n`;
        md += `**Rank:** ${rankInfo.average_rank.toFixed(1)}\n\n`;
        
        if (s1) {
            const s1Stats = formatStats(s1.elapsed_time, s1.cost);
            md += `**Stage 1:** ${s1Stats}\n\n`;
        }
        if (s2) {
            const s2Stats = formatStats(s2.elapsed_time, s2.cost);
            md += `**Stage 2:** ${s2Stats}\n\n`;
        }

        if (s1) {
          // Increase heading levels so content is nested under the model section
          const nestedResponse = increaseHeadingLevels(s1.response);
          // Always wrap with Response section to ensure expandability
          md += `### Response\n\n`;
          md += `${nestedResponse}\n\n`;
        }
        md += `---\n\n`;
      });
    }

    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="stage stage3">
      <div className="stage-header">
        <h3 className="stage-title">Stage 3: Final Council Answer</h3>
        <button className="export-button" onClick={handleExport} title="Download report as Markdown">
          Export Report
        </button>
      </div>
      <div className="final-response">
        <div className="model-header">
          <span className="chairman-label">
            Chairman: {finalResponse.model.split('/')[1] || finalResponse.model}
          </span>
          {stats && <span className="model-stats-inline">{stats}</span>}
        </div>
        {totalStats && (
          <div className="total-stats">
            <span className="total-stats-label">Elapsed running time and total cost:</span>
            <span className="total-stats-value">{totalStats}</span>
            {(webSearch || quickMode || codingMode) && (
              <span className="run-mode-badges">
                {webSearch && <span className="run-mode-badge badge-search">🔍 Search</span>}
                {codingMode && <span className="run-mode-badge badge-coding">💻 Code</span>}
                {quickMode && <span className="run-mode-badge badge-quick">⚡ Quick</span>}
              </span>
            )}
          </div>
        )}
        <div className="final-text markdown-content">
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
            {convertLatexDelimiters(finalResponse.response)}
          </ReactMarkdown>
        </div>
        {finalResponse.custom_chairman_instructions && (
          <div className="chairman-footnote">
            * Custom chairman instructions in effect
          </div>
        )}
      </div>
    </div>
  );
}
