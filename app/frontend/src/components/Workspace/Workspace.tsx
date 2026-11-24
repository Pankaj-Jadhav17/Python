import React, { useState, FormEvent, useRef, useEffect } from 'react';
import { ChatMessage, CollectionSummary, GraphNode, GraphEdge } from '../../types/graph';
import { SourceCitationCard } from './SourceCitationCard';
import { RelatedSubgraph } from './RelatedSubgraph';
import {
  SparklesIcon,
  SendIcon,
  BookOpenIcon,
  CloseIcon,
  AlertCircleIcon,
  GraphIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PanelLeftOpenIcon,
} from '../Common/Icons';

type WorkspaceProps = {
  activeCollection: CollectionSummary | undefined;
  messages: ChatMessage[];
  isAsking: boolean;
  onAsk: (question: string) => Promise<void>;
  selectedNode: GraphNode | null;
  onClearSelectedNode: () => void;
  onSelectNode: (node: GraphNode | null) => void;
  onSelectEdge: (edge: GraphEdge | null) => void;
  apiError?: string | null;
  isLeftSidebarCollapsed?: boolean;
  onToggleLeftSidebar?: () => void;
  isGraphPanelCollapsed?: boolean;
  onToggleGraphPanel?: () => void;
};

export const Workspace: React.FC<WorkspaceProps> = ({
  activeCollection,
  messages,
  isAsking,
  onAsk,
  selectedNode,
  onClearSelectedNode,
  onSelectNode,
  onSelectEdge,
  apiError,
  isLeftSidebarCollapsed,
  onToggleLeftSidebar,
  isGraphPanelCollapsed,
  onToggleGraphPanel,
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, isAsking]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const query = inputValue.trim();
    if (!query || isAsking) {
      if (selectedNode && !isAsking) {
        await onAsk(`Explain the concept "${selectedNode.label}" in the context of this collection.`);
      }
      return;
    }
    setInputValue('');
    await onAsk(query);
  }

  const placeholderText = selectedNode
    ? `Ask about "${selectedNode.label}"...`
    : activeCollection
    ? `Ask a question about "${activeCollection.name}"...`
    : 'Ask a question about your selected documents...';

  return (
    <section className="workspace-container" aria-label="Question & Answer Workspace">
      {/* Workspace Header */}
      <header className="workspace-header">
        <div className="workspace-header-controls-row">
          <div className="workspace-header-left">
            {isLeftSidebarCollapsed && onToggleLeftSidebar && (
              <button
                type="button"
                className="layout-toggle-btn expand-sidebar-btn"
                onClick={onToggleLeftSidebar}
                title="Show left sidebar (Collections & Documents)"
                aria-label="Show left sidebar"
              >
                <PanelLeftOpenIcon size={16} />
                <span>Show Sidebar</span>
              </button>
            )}

            <div className="header-badge-row">
              <span className="collection-active-pill">
                {activeCollection ? activeCollection.name : 'No Collection Selected'}
              </span>
              <span className="grounded-badge">
                <span className="grounded-dot" /> Grounded Graph RAG
              </span>
            </div>
          </div>

          <div className="workspace-header-right">
            {onToggleGraphPanel && (
              <button
                type="button"
                className={`layout-toggle-btn ${isGraphPanelCollapsed ? 'expand-graph-btn' : 'collapse-graph-btn'}`}
                onClick={onToggleGraphPanel}
                title={isGraphPanelCollapsed ? "Show Knowledge Graph" : "Collapse Knowledge Graph (expand workspace)"}
                aria-label={isGraphPanelCollapsed ? "Show Knowledge Graph" : "Collapse Knowledge Graph"}
              >
                <GraphIcon size={15} />
                <span>{isGraphPanelCollapsed ? "Show Graph" : "Hide Graph"}</span>
                {isGraphPanelCollapsed ? <ChevronLeftIcon size={14} /> : <ChevronRightIcon size={14} />}
              </button>
            )}
          </div>
        </div>

        <div className="workspace-title-group">
          <h2 className="workspace-title">Q&A Workspace</h2>
          <p className="workspace-subtitle">
            Synthesizes answers with multi-hop graph reasoning and verifiable source citations.
          </p>
        </div>
      </header>

      {/* API Error Banner if present */}
      {apiError && (
        <div className="api-error-banner" role="alert">
          <AlertCircleIcon size={16} className="error-banner-icon" />
          <span>{apiError}</span>
        </div>
      )}

      {/* Messages Feed or Empty State */}
      <div className="workspace-messages-feed" aria-live="polite">
        {messages.length === 0 ? (
          <div className="empty-workspace-state">
            <div className="empty-workspace-card">
              <div className="empty-icon-halo">
                <SparklesIcon size={28} className="empty-sparkle-icon" />
              </div>
              <h3 className="empty-state-title">Ask anything about your documents.</h3>
              <p className="empty-state-description">
                Ask questions about any concepts, connections, or claims across your uploaded PDFs.
                Every answer will be supported by actual graph reasoning paths and original document citations.
              </p>
              {selectedNode && (
                <button
                  type="button"
                  className="quick-concept-btn"
                  onClick={() => onAsk(`Explain the concept "${selectedNode.label}" in the context of this collection.`)}
                >
                  <SparklesIcon size={14} />
                  <span>Ask about selected concept: &ldquo;{selectedNode.label}&rdquo;</span>
                </button>
              )}
            </div>
          </div>
        ) : (
          messages.map((msg) => (
            <div
              key={msg.id}
              className={`chat-message-row ${msg.role === 'user' ? 'user-row' : 'assistant-row'}`}
            >
              {msg.role === 'user' ? (
                <div className="user-message-bubble">
                  <div className="bubble-role-bar">
                    <span className="role-label user-label">You</span>
                    <span className="timestamp-label">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p className="user-query-text">{msg.content}</p>
                </div>
              ) : (
                <div className="assistant-message-bubble">
                  <div className="bubble-role-bar">
                    <div className="assistant-badge">
                      <SparklesIcon size={13} className="assistant-sparkle" />
                      <span className="role-label">Graph Assistant</span>
                    </div>
                    <span className="timestamp-label">
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>

                  {/* Main Answer Text */}
                  <div className="assistant-answer-text">
                    <p>{msg.content}</p>
                  </div>

                  {/* Related Subgraph Card */}
                  {msg.answerPath && (
                    <div className="answer-subgraph-section">
                      <RelatedSubgraph
                        path={msg.answerPath}
                        onSelectNode={onSelectNode}
                        onSelectEdge={onSelectEdge}
                      />
                    </div>
                  )}

                  {/* Source Evidence Citations */}
                  <div className="answer-evidence-section">
                    <div className="evidence-section-header">
                      <BookOpenIcon size={14} className="evidence-header-icon" />
                      <h4>
                        Source Citations{' '}
                        {msg.evidence && msg.evidence.length > 0 && (
                          <span className="evidence-count">({msg.evidence.length})</span>
                        )}
                      </h4>
                    </div>

                    {msg.evidence && msg.evidence.length > 0 ? (
                      <div className="citations-grid">
                        {msg.evidence.map((item, idx) => (
                          <SourceCitationCard
                            key={item.passage_id || item.passageId || item.episode_id || idx}
                            evidence={item}
                            index={idx}
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="no-evidence-text">No supporting passages were returned.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))
        )}

        {/* Thinking State */}
        {isAsking && (
          <div className="chat-message-row assistant-row">
            <div className="assistant-message-bubble thinking-bubble">
              <div className="thinking-row">
                <span className="spinner-sm" />
                <span className="thinking-text">Preparing your knowledge graph... Exploring connections and retrieving evidence.</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom Question Input Bar */}
      <footer className="workspace-input-container">
        {selectedNode && (
          <div className="focused-node-chip">
            <span>Focused Concept: <strong>{selectedNode.label}</strong></span>
            <button
              type="button"
              className="chip-dismiss-btn"
              onClick={onClearSelectedNode}
              title="Clear focused concept"
            >
              <CloseIcon size={12} />
            </button>
          </div>
        )}

        <form className="workspace-input-form" onSubmit={handleSubmit}>
          <input
            type="text"
            className="workspace-text-input"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={placeholderText}
            disabled={isAsking}
            maxLength={2000}
            autoFocus
          />

          <button
            type="submit"
            className="workspace-send-btn"
            disabled={(!inputValue.trim() && !selectedNode) || isAsking}
            title="Ask question"
            aria-label="Send question"
          >
            {isAsking ? <span className="spinner-sm" /> : <SendIcon size={16} />}
            <span className="send-btn-label">Ask</span>
          </button>
        </form>
      </footer>
    </section>
  );
};
