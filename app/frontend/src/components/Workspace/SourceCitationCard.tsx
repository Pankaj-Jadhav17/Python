import React from 'react';
import { EvidenceItem } from '../../types/graph';
import { FileTextIcon } from '../Common/Icons';

type SourceCitationCardProps = {
  evidence: EvidenceItem;
  index: number;
};

export const SourceCitationCard: React.FC<SourceCitationCardProps> = ({ evidence, index }) => {
  const docName = evidence.document_name || evidence.documentName || 'Document';
  const text = evidence.text || evidence.evidence || '';
  const page = evidence.page;
  const chunk = evidence.chunk_index;
  const confidence = evidence.confidence ?? evidence.score;

  return (
    <article className="source-citation-card" aria-label={`Evidence passage ${index + 1}`}>
      <div className="citation-header">
        <div className="citation-doc-tag">
          <FileTextIcon size={12} className="citation-icon" />
          <strong className="citation-doc-name" title={docName}>{docName}</strong>
        </div>

        <div className="citation-pills">
          {page !== undefined && page !== null && (
            <span className="citation-meta-pill page-pill">Page {page}</span>
          )}
          {chunk !== undefined && chunk !== null && (
            <span className="citation-meta-pill chunk-pill">Chunk {chunk + 1}</span>
          )}
          {confidence !== undefined && confidence !== null && (
            <span className="citation-meta-pill conf-pill" title="Relevance confidence">
              {(confidence * 100).toFixed(0)}% match
            </span>
          )}
        </div>
      </div>

      <blockquote className="citation-quote">
        <p>{text}</p>
      </blockquote>
    </article>
  );
};
