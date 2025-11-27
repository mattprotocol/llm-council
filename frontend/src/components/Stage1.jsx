import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './Stage1.css';

export default function Stage1({ responses, streaming, toolResult }) {
  const [activeTab, setActiveTab] = useState(0);

  // Get models from either completed responses or streaming state
  const models = responses?.length > 0 
    ? responses.map(r => r.model)
    : streaming ? Object.keys(streaming) : [];

  if (models.length === 0 && !toolResult) {
    return null;
  }

  const currentModel = models[activeTab];
  const completedResponse = responses?.find(r => r.model === currentModel);
  const streamingData = streaming?.[currentModel];
  
  // Use completed response if available, otherwise show streaming content
  const displayContent = completedResponse?.response || streamingData?.content || '';
  const thinkingContent = streamingData?.thinking || '';
  const isStreaming = streamingData?.isStreaming && !completedResponse;
  const tokensPerSecond = streamingData?.tokensPerSecond;
  const thinkingSeconds = streamingData?.thinkingSeconds;
  const elapsedSeconds = streamingData?.elapsedSeconds;

  // Format timing as "thinking/total"
  const formatTiming = (thinking, elapsed) => {
    if (elapsed === undefined) return null;
    const t = thinking !== undefined ? thinking : elapsed;
    return `${t}s/${elapsed}s`;
  };

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      {/* Show tool result if available */}
      {toolResult && (
        <div className="tool-result-card">
          <div className="tool-result-header">
            <span className="tool-icon">🔧</span>
            <span className="tool-name">MCP Tool: {toolResult.tool}</span>
          </div>
          <div className="tool-result-body">
            <div className="tool-io">
              <span className="tool-label">Input:</span>
              <code className="tool-value">{JSON.stringify(toolResult.input)}</code>
            </div>
            <div className="tool-io">
              <span className="tool-label">Output:</span>
              <code className="tool-value">{JSON.stringify(toolResult.output)}</code>
            </div>
          </div>
        </div>
      )}

      {models.length > 0 && (
        <>
          <div className="tabs">
            {models.map((model, index) => {
              const modelStreaming = streaming?.[model];
              const modelComplete = responses?.find(r => r.model === model);
              const hasContent = modelComplete || modelStreaming?.content;
              const modelTps = modelStreaming?.tokensPerSecond;
              const modelTiming = modelStreaming?.elapsedSeconds !== undefined 
                ? `${modelStreaming?.thinkingSeconds ?? modelStreaming?.elapsedSeconds}s/${modelStreaming?.elapsedSeconds}s`
                : null;
              
              return (
                <button
                  key={index}
                  className={`tab ${activeTab === index ? 'active' : ''} ${modelStreaming?.isStreaming && !modelComplete ? 'streaming' : ''}`}
                  onClick={() => setActiveTab(index)}
                >
                  {model.split('/')[1] || model}
                  {modelStreaming?.isStreaming && !modelComplete && modelTiming && <span className="timing-indicator">{modelTiming}</span>}
                  {modelStreaming?.isStreaming && !modelComplete && <span className="streaming-indicator">●</span>}
                </button>
              );
            })}
          </div>

          <div className="tab-content">
            <div className="model-name">
              {currentModel}
              {tokensPerSecond !== undefined && <span className="tps-badge">{tokensPerSecond.toFixed(1)} tok/s</span>}
              {formatTiming(thinkingSeconds, elapsedSeconds) && <span className="timing-badge">{formatTiming(thinkingSeconds, elapsedSeconds)}</span>}
              {isStreaming && <span className="streaming-badge">Streaming...</span>}
            </div>
            
            {thinkingContent && (
              <details className="thinking-section" open={isStreaming}>
                <summary>Thinking</summary>
                <div className="thinking-content">
                  {thinkingContent}
                </div>
              </details>
            )}
            
            <div className="response-text markdown-content">
              <ReactMarkdown>{displayContent}</ReactMarkdown>
              {isStreaming && <span className="cursor-blink">▌</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
