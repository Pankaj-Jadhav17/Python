import React from 'react';
import { GraphEdge } from '../../types/graph';
import { CloseIcon, BookOpenIcon, FileTextIcon } from '../Common/Icons';

type EdgeDetailDrawerProps = {
  edge: GraphEdge;
  sourceLabel: string;
  targetLabel: string;
  onClose: () => void;
};

export const EdgeDetailDrawer: React.FC<EdgeDetailDrawerProps> = ({
  edge,
  sourceLabel,
  targetLabel,
  onClose,
}) => {
  const records = edge.evidence_records ?? [];

  return (
    <aside className="inspection-drawer edge-drawer" aria-label="Relationship Provenance">
      <div className="drawer-header">
        <div className="drawer-title-group">
          <span className="drawer-eyebrow">Relationship Provenance</span>
          <h3 className="drawer-title edge-path-title">
            <span className="endpoint-node">{sourceLabel}</span>
            <span className="edge-rel-arrow">─[{edge.label}]→</span>
            <span className="endpoint-node">{targetLabel}</span>
          </h3>
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
        {/* Multi-Evidence Records */}
        {records.length > 0 ? (
          <div className="drawer-evidence-list">
            <div className="evidence-list-header">
              <BookOpenIcon size={14} />
              <span>Supported by {records.length} passage{records.length === 1 ? '' : 's'}:</span>
            </div>

            <div className="evidence-records-scroll">
              {records.map((rec, idx) => (
                <div key={idx} className="edge-evidence-card">
                  {rec.evidence ? (
                    <blockquote className="edge-evidence-quote">{rec.evidence}</blockquote>
                  ) : (
                    <p className="no-text-evidence">Passage recorded without text quote.</p>
                  )}

                  <div className="edge-evidence-meta">
                    {rec.document_name && (
                      <span className="edge-meta-item">
                        <FileTextIcon size={11} />
                        <strong>{rec.document_name}</strong>
                      </span>
                    )}
                    {rec.page !== undefined && rec.page !== null && (
                      <span className="edge-meta-item">
                        Page <strong>{rec.page}</strong>
                      </span>
                    )}
                    {rec.passage_id && (
                      <span className="edge-meta-item">
                        ID: <code>{rec.passage_id.slice(0, 8)}</code>
                      </span>
                    )}
                    {rec.confidence !== undefined && (
                      <span className="edge-meta-item">
                        Confidence: <strong>{(rec.confidence * 100).toFixed(0)}%</strong>
                      </span>
                    )}
                    {rec.status && (
                      <span className={`status-pill ${rec.status}`}>
                        {rec.status}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : edge.evidence ? (
          <div className="edge-evidence-card">
            <blockquote className="edge-evidence-quote">{edge.evidence}</blockquote>
          </div>
        ) : (
          <p className="no-evidence-text">This connection has no stored evidence quote.</p>
        )}

        <div className="edge-footer-meta">
          {edge.document_names && edge.document_names.length > 0 && (
            <div className="footer-meta-row">
              <span className="meta-label">Documents:</span>
              <span className="meta-value">{edge.document_names.filter(Boolean).join(', ')}</span>
            </div>
          )}
          {edge.confidence !== undefined && (
            <div className="footer-meta-row">
              <span className="meta-label">Confidence:</span>
              <span className="meta-value">{(edge.confidence * 100).toFixed(0)}%</span>
            </div>
          )}
          {edge.status && (
            <div className="footer-meta-row">
              <span className="meta-label">Status:</span>
              <span className={`status-pill ${edge.status}`}>{edge.status}</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
