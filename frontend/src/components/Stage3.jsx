import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { convertLatexDelimiters } from '../utils/latex';
import { formatStats } from '../utils/stats';
import { generateStatsGraph } from '../utils/graph';
import './Stage3.css';

export default function Stage3({ finalResponse, stage1, stage2, aggregateRankings }) {
  if (!finalResponse) {
    return null;
  }

  const stats = formatStats(finalResponse.elapsed_time, finalResponse.cost);

  // Helper function to increase all markdown heading levels by 1
  const increaseHeadingLevels = (markdown) => {
    return markdown.replace(/^(#{1,5}) /gm, '#$1 ');
  };

  const handleExport = () => {
    let md = `# Final Council Answer\n\n`;
    md += `**Chairman:** ${finalResponse.model}\n`;
    md += `**Stats:** ${stats || 'N/A'}\n\n`;
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
    a.download = 'council_report.md';
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
        <div className="final-text markdown-content">
          <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
            {convertLatexDelimiters(finalResponse.response)}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
