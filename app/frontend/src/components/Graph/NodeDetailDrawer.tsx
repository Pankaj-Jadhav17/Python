import React from 'react';
import { GraphNode } from '../../types/graph';
import { CloseIcon, SparklesIcon, FileTextIcon } from '../Common/Icons';

type NodeDetailDrawerProps = {
  node: GraphNode;
  onClose: () => void;
  onAskAboutNode: (node: GraphNode) => void;
};

export const NodeDetailDrawer: React.FC<NodeDetailDrawerProps> = ({
  node,
  onClose,
  onAskAboutNode,
}) => {
  return (
    <aside className="inspection-drawer node-drawer" aria-label="Concept Details">
      <div className="drawer-header">
        <div className="drawer-title-group">
          <span className="drawer-eyebrow">Concept Inspection</span>
          <h3 className="drawer-title">{node.label}</h3>
        </div>
        <button
          type="button"
          className="drawer-close-btn"
          onClick={onClose}
          aria-label="Close details"
        >
          <CloseIcon size={16} />
        </button>
      </div>

      <div className="drawer-body">
        <div className="drawer-meta-grid">
          <div className="meta-card">
            <span className="meta-label">Type</span>
            <strong className="meta-value">{node.entity_type || node.type}</strong>
          </div>

          {node.community_id !== undefined && node.community_id >= 0 && (
            <div className="meta-card">
              <span className="meta-label">Topic Group</span>
              <strong className="meta-value">Group {node.community_id + 1}</strong>
            </div>
          )}

          {node.aliases && node.aliases.length > 0 && (
            <div className="meta-card span-full">
              <span className="meta-label">Aliases</span>
              <strong className="meta-value">{node.aliases.join(', ')}</strong>
            </div>
          )}
        </div>

        {node.documents && node.documents.length > 0 && (
          <div className="drawer-docs-section">
            <span className="section-small-title">Mentioned in Documents:</span>
            <div className="drawer-doc-tags">
              {node.documents.map((doc, idx) => (
                <span key={`${doc}-${idx}`} className="drawer-doc-tag">
                  <FileTextIcon size={11} />
                  <span>{doc}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="drawer-actions">
          <button
            type="button"
            className="btn-ask-concept"
            onClick={() => onAskAboutNode(node)}
          >
            <SparklesIcon size={14} />
            <span>Ask about &ldquo;{node.label}&rdquo;</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
