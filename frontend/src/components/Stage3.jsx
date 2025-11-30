import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { convertLatexDelimiters } from '../utils/latex';
import { formatStats } from '../utils/stats';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  const stats = formatStats(finalResponse.elapsed_time, finalResponse.cost);

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
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
