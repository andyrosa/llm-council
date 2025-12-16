import { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

export default function ChatInterface({
  conversation,
  conversationTitle,
  onSendMessage,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const [webSearchMode, setWebSearchMode] = useState('auto'); // 'auto' | 'on' | 'off'
  const [webSearchAnimating, setWebSearchAnimating] = useState(false);
  const [codingMode, setCodingMode] = useState('auto'); // 'auto' | 'on' | 'off'
  const [codingAnimating, setCodingAnimating] = useState(false);
  const [majorityMode, setMajorityMode] = useState('auto'); // 'auto' | 'on' | 'off'
  const [majorityAnimating, setMajorityAnimating] = useState(false);
  const messagesEndRef = useRef(null);

  const hasWebSearchWord = /\b(search|today|recent|news)\b/i.test(input);
  const autoWebSearchDetected = webSearchMode === 'auto' && hasWebSearchWord;
  const webSearchEnabled = webSearchMode === 'on' || autoWebSearchDetected;

  const hasCodingWord = /\b(code|program|programming|function|script|debug)\b/i.test(input);
  const autoCodingDetected = codingMode === 'auto' && hasCodingWord;
  const codingEnabled = codingMode === 'on' || autoCodingDetected;

  const hasMajorityWord = /\b(quick|majority)\b/i.test(input);
  const autoMajorityDetected = majorityMode === 'auto' && hasMajorityWord;
  const majorityEnabled = majorityMode === 'on' || autoMajorityDetected;

  // Animate when auto-detection triggers web search
  useEffect(() => {
    // Avoid calling setState synchronously inside the effect (which can
    // trigger cascading renders). Schedule the animation start asynchronously
    // so the update does not happen during the render/effect phase.
    if (webSearchMode === 'auto' && hasWebSearchWord) {
      const startTimer = setTimeout(() => setWebSearchAnimating(true), 0);
      const stopTimer = setTimeout(() => setWebSearchAnimating(false), 600);
      return () => {
        clearTimeout(startTimer);
        clearTimeout(stopTimer);
      };
    }
  }, [hasWebSearchWord, webSearchMode]);

  // Animate when auto-detection triggers coding mode
  useEffect(() => {
    if (codingMode === 'auto' && hasCodingWord) {
      const startTimer = setTimeout(() => setCodingAnimating(true), 0);
      const stopTimer = setTimeout(() => setCodingAnimating(false), 600);
      return () => {
        clearTimeout(startTimer);
        clearTimeout(stopTimer);
      };
    }
  }, [hasCodingWord, codingMode]);

  // Animate when auto-detection triggers majority mode
  useEffect(() => {
    if (majorityMode === 'auto' && hasMajorityWord) {
      const startTimer = setTimeout(() => setMajorityAnimating(true), 0);
      const stopTimer = setTimeout(() => setMajorityAnimating(false), 600);
      return () => {
        clearTimeout(startTimer);
        clearTimeout(stopTimer);
      };
    }
  }, [hasMajorityWord, majorityMode]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  const handleWebSearchToggle = () => {
    if (webSearchMode === 'auto') {
      setWebSearchMode('on');
    } else if (webSearchMode === 'on') {
      setWebSearchMode('off');
    } else {
      setWebSearchMode('auto');
    }
  };

  const handleCodingToggle = () => {
    if (codingMode === 'auto') {
      setCodingMode('on');
    } else if (codingMode === 'on') {
      setCodingMode('off');
    } else {
      setCodingMode('auto');
    }
  };

  const handleMajorityToggle = () => {
    if (majorityMode === 'auto') {
      setMajorityMode('on');
    } else if (majorityMode === 'on') {
      setMajorityMode('off');
    } else {
      setMajorityMode('auto');
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input, webSearchEnabled, majorityEnabled, codingEnabled);
      setInput('');
      setWebSearchMode('auto');
      setCodingMode('auto');
      setMajorityMode('auto');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="empty-state">
          <h2>Welcome to LLM Council</h2>
          <p>Create a new conversation to get started</p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        {conversation.messages.length === 0 ? (
          <div className="empty-state">
            <h2>Start a conversation</h2>
            <p>Ask a question to consult the LLM Council</p>
          </div>
        ) : (
          conversation.messages.map((msg, index) => (
            <div key={index} className="message-group">
              {msg.role === 'user' ? (
                <div className="user-message">
                  <div className="message-label">You</div>
                  <div className="message-content">
                    <div className="markdown-content">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="assistant-message">
                  <div className="message-label">LLM Council</div>

                  {/* Stage 1 */}
                  {msg.loading?.stage1 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>
                        Running Stage 1: Collecting individual responses...
                        {msg.progress?.stage1?.total > 0 && (
                          <span className="progress-indicator">
                            {' '}({msg.progress.stage1.completed}/{msg.progress.stage1.total})
                            {msg.progress.stage1.majorityReached && ' ✓ Majority reached'}
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                  {msg.stage1 && (
                    <Stage1 
                      responses={msg.stage1} 
                      progress={msg.progress?.stage1}
                    />
                  )}

                  {/* Stage 2 */}
                  {msg.loading?.stage2 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>
                        Running Stage 2: Peer rankings...
                        {msg.progress?.stage2?.total > 0 && (
                          <span className="progress-indicator">
                            {' '}({msg.progress.stage2.completed}/{msg.progress.stage2.total})
                            {msg.progress.stage2.majorityReached && ' ✓ Majority reached'}
                          </span>
                        )}
                      </span>
                    </div>
                  )}
                  {msg.stage2 && (
                    <Stage2
                      rankings={msg.stage2}
                      labelToModel={msg.metadata?.label_to_model}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                      progress={msg.progress?.stage2}
                      stage1={msg.stage1}
                    />
                  )}

                  {/* Stage 3 */}
                  {msg.loading?.stage3 && (
                    <div className="stage-loading">
                      <div className="spinner"></div>
                      <span>Running Stage 3: Final synthesis...</span>
                    </div>
                  )}
                  {msg.stage3 && (
                    <Stage3
                      finalResponse={msg.stage3}
                      stage1={msg.stage1}
                      stage2={msg.stage2}
                      aggregateRankings={msg.metadata?.aggregate_rankings}
                      conversationTitle={conversationTitle}
                      elapsedRunningTime={msg.elapsed_running_time}
                      totalCost={msg.total_cost}
                      webSearch={msg.web_search}
                      quickMode={msg.quick_mode}
                      codingMode={msg.coding_mode}
                    />
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="loading-indicator">
            <div className="spinner"></div>
            <span>Waiting for all stages to complete...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {conversation.messages.length === 0 && (
        <form className="input-form" onSubmit={handleSubmit}>
          <textarea
            className="message-input"
            placeholder="Ask your question... (Shift+Enter for new line, Enter to send)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <div className="input-actions">
            <div className="toggle-group">
              <label
                className={`web-search-toggle ${webSearchAnimating ? 'animating' : ''} ${webSearchEnabled ? 'enabled' : ''}`}
                onClick={handleWebSearchToggle}
              >
                <span className={`web-search-indicator ${webSearchEnabled ? 'on' : 'off'}`} />
                <span className="web-search-label">
                  Web {webSearchMode === 'auto' ? '(auto)' : webSearchMode === 'on' ? 'on' : 'off'}
                </span>
              </label>
              <label
                className={`coding-toggle ${codingAnimating ? 'animating' : ''} ${codingEnabled ? 'enabled' : ''}`}
                onClick={handleCodingToggle}
              >
                <span className={`coding-indicator ${codingEnabled ? 'on' : 'off'}`} />
                <span className="coding-label">
                  Code {codingMode === 'auto' ? '(auto)' : codingMode === 'on' ? 'on' : 'off'}
                </span>
              </label>
              <label
                className={`majority-toggle ${majorityAnimating ? 'animating' : ''} ${majorityEnabled ? 'enabled' : ''}`}
                onClick={handleMajorityToggle}
              >
                <span className={`majority-indicator ${majorityEnabled ? 'on' : 'off'}`} />
                <span className="majority-label">
                  Quick {majorityMode === 'auto' ? '(auto)' : majorityMode === 'on' ? 'on' : 'off'}
                </span>
              </label>
            </div>
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading}
            >
              Send
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
