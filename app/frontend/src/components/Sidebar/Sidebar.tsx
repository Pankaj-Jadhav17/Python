import React, { useState, useRef, ChangeEvent, FormEvent, DragEvent } from 'react';
import { CollectionSummary, DocumentSummary, TopicGroup, KeyTerm } from '../../types/graph';
import {
  DatabaseIcon,
  FolderIcon,
  FileTextIcon,
  UploadCloudIcon,
  PlusIcon,
  CloseIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  PanelLeftCloseIcon,
} from '../Common/Icons';

type SidebarProps = {
  collections: CollectionSummary[];
  selectedCollectionId: string;
  onSelectCollection: (colId: string) => void;
  onCreateCollection: (name: string, description?: string) => Promise<void>;
  documents: DocumentSummary[];
  selectedDocument: string;
  onSelectDocument: (docName: string) => void;
  onUploadDocuments: (files: File[]) => Promise<void>;
  isUploading: boolean;
  uploadStatusMessage: string;
  topicGroups?: TopicGroup[];
  selectedTopicId?: string | number | null;
  onSelectTopic?: (topicId: string | number | null) => void;
  keyTerms?: KeyTerm[];
  selectedTermId?: string | null;
  onSelectTerm?: (term: KeyTerm) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
};

export const Sidebar: React.FC<SidebarProps> = ({
  collections,
  selectedCollectionId,
  onSelectCollection,
  onCreateCollection,
  documents,
  selectedDocument,
  onSelectDocument,
  onUploadDocuments,
  isUploading,
  uploadStatusMessage,
  topicGroups,
  selectedTopicId,
  onSelectTopic,
  keyTerms,
  selectedTermId,
  onSelectTerm,
  isCollapsed,
  onToggleCollapse,
}) => {
  // Independent Section Expand/Collapse State
  const [isCollectionsExpanded, setIsCollectionsExpanded] = useState(true);
  const [isDocumentsExpanded, setIsDocumentsExpanded] = useState(true);

  // Collection creation state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newColName, setNewColName] = useState('');
  const [newColDesc, setNewColDesc] = useState('');
  const [isCreatingCol, setIsCreatingCol] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Upload files state (queue)
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const activeCollection = collections.find((c) => c.collection_id === selectedCollectionId);

  // Documents in active collection
  const collectionDocs = documents.filter(
    (d) => !d.collection_id || d.collection_id === selectedCollectionId
  );

  async function handleCreateSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newColName.trim()) return;
    setIsCreatingCol(true);
    setCreateError(null);
    try {
      await onCreateCollection(newColName.trim(), newColDesc.trim() || undefined);
      setNewColName('');
      setNewColDesc('');
      setShowCreateModal(false);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Could not create collection');
    } finally {
      setIsCreatingCol(false);
    }
  }

  function handleFileSelect(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      const filesArray = Array.from(e.target.files);
      setStagedFiles((prev) => [...prev, ...filesArray]);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArray = Array.from(e.dataTransfer.files);
      setStagedFiles((prev) => [...prev, ...filesArray]);
    }
  }

  function removeStagedFile(index: number) {
    setStagedFiles((prev) => prev.filter((_, i) => i !== index));
  }

  async function startUpload() {
    if (stagedFiles.length === 0 || isUploading) return;
    const filesToUpload = [...stagedFiles];
    setStagedFiles([]);
    await onUploadDocuments(filesToUpload);
  }

  return (
    <aside className="sidebar-container" aria-label="Collections and Navigation">
      {/* App Branding */}
      <div className="sidebar-header">
        <div className="brand-badge">
          <div className="brand-logo-glow" />
          <DatabaseIcon size={20} className="brand-icon" />
          <div className="brand-text">
            <span className="brand-title">Graphroom</span>
            <span className="brand-subtitle">Dynamic GraphRAG</span>
          </div>
        </div>
        {onToggleCollapse && (
          <button
            type="button"
            className="sidebar-collapse-toggle-btn"
            onClick={onToggleCollapse}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
          >
            <PanelLeftCloseIcon size={16} />
          </button>
        )}
      </div>

      <div className="sidebar-scrollable">
        {/* COLLECTIONS SECTION */}
        <section className={`sidebar-section ${isCollectionsExpanded ? 'section-open' : 'section-collapsed'}`}>
          <div className="section-header">
            <button
              type="button"
              className="section-title-toggle-btn"
              onClick={() => setIsCollectionsExpanded((prev) => !prev)}
              aria-expanded={isCollectionsExpanded}
              title={isCollectionsExpanded ? 'Collapse Collections' : 'Expand Collections'}
            >
              <span className={`section-chevron-wrap ${isCollectionsExpanded ? 'expanded' : 'collapsed'}`}>
                {isCollectionsExpanded ? <ChevronDownIcon size={13} /> : <ChevronRightIcon size={13} />}
              </span>
              <FolderIcon size={14} className="section-icon" />
              <h3>Collections</h3>
              <span className="count-pill">{collections.length}</span>
            </button>
            <div className="section-header-actions">
              <button
                type="button"
                className="action-icon-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setShowCreateModal((prev) => !prev);
                  if (!isCollectionsExpanded) setIsCollectionsExpanded(true);
                }}
                title="Create new collection"
                aria-label="New collection"
              >
                <PlusIcon size={14} />
              </button>
              <button
                type="button"
                className="action-icon-btn section-toggle-btn"
                onClick={() => setIsCollectionsExpanded((prev) => !prev)}
                title={isCollectionsExpanded ? 'Collapse Collections section' : 'Expand Collections section'}
                aria-label={isCollectionsExpanded ? 'Collapse Collections section' : 'Expand Collections section'}
                aria-expanded={isCollectionsExpanded}
              >
                {isCollectionsExpanded ? <ChevronDownIcon size={13} /> : <ChevronRightIcon size={13} />}
              </button>
            </div>
          </div>

          {/* Collapsible Collections Body */}
          {isCollectionsExpanded && (
            <div className="section-collapsible-body">
              {/* Inline Create Collection Panel */}
              {showCreateModal && (
                <form className="create-collection-card" onSubmit={handleCreateSubmit}>
                  <div className="create-card-header">
                    <span>New Collection</span>
                    <button
                      type="button"
                      className="close-sm-btn"
                      onClick={() => setShowCreateModal(false)}
                    >
                      <CloseIcon size={12} />
                    </button>
                  </div>
                  <input
                    type="text"
                    placeholder="Collection name..."
                    value={newColName}
                    onChange={(e) => setNewColName(e.target.value)}
                    autoFocus
                    required
                    className="sidebar-input"
                  />
                  <input
                    type="text"
                    placeholder="Optional description"
                    value={newColDesc}
                    onChange={(e) => setNewColDesc(e.target.value)}
                    className="sidebar-input"
                  />
                  {createError && <p className="sidebar-error">{createError}</p>}
                  <div className="create-actions">
                    <button
                      type="button"
                      className="btn-cancel"
                      onClick={() => setShowCreateModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      className="btn-primary-sm"
                      disabled={!newColName.trim() || isCreatingCol}
                    >
                      {isCreatingCol ? 'Creating...' : 'Create'}
                    </button>
                  </div>
                </form>
              )}

              {/* Collection List */}
              <div className="collections-list">
                {collections.length === 0 ? (
                  <p className="empty-hint">Create or select a collection to get started.</p>
                ) : (
                  collections.map((col) => {
                    const isSelected = col.collection_id === selectedCollectionId;
                    return (
                      <button
                        key={col.collection_id}
                        type="button"
                        className={`collection-item ${isSelected ? 'active' : ''}`}
                        onClick={() => onSelectCollection(col.collection_id)}
                      >
                        <div className="collection-item-header">
                          <FolderIcon size={14} className="collection-folder-icon" />
                          <strong className="collection-item-name">{col.name}</strong>
                        </div>
                        <div className="collection-meta-row">
                          <span>{col.document_count} doc{col.document_count === 1 ? '' : 's'}</span>
                          <span className="meta-bullet">•</span>
                          <span>{col.relationship_count} relations</span>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          )}
        </section>

        {/* DOCUMENTS SECTION */}
        <section className={`sidebar-section ${isDocumentsExpanded ? 'section-open' : 'section-collapsed'}`}>
          <div className="section-header">
            <button
              type="button"
              className="section-title-toggle-btn"
              onClick={() => setIsDocumentsExpanded((prev) => !prev)}
              aria-expanded={isDocumentsExpanded}
              title={isDocumentsExpanded ? 'Collapse Documents' : 'Expand Documents'}
            >
              <span className={`section-chevron-wrap ${isDocumentsExpanded ? 'expanded' : 'collapsed'}`}>
                {isDocumentsExpanded ? <ChevronDownIcon size={13} /> : <ChevronRightIcon size={13} />}
              </span>
              <FileTextIcon size={14} className="section-icon" />
              <h3>Documents</h3>
              <span className="count-pill">{collectionDocs.length}</span>
            </button>
            <div className="section-header-actions">
              {activeCollection && (
                <span className="active-col-tag" title={`Active: ${activeCollection.name}`}>
                  {activeCollection.name}
                </span>
              )}
              <button
                type="button"
                className="action-icon-btn section-toggle-btn"
                onClick={() => setIsDocumentsExpanded((prev) => !prev)}
                title={isDocumentsExpanded ? 'Collapse Documents section' : 'Expand Documents section'}
                aria-label={isDocumentsExpanded ? 'Collapse Documents section' : 'Expand Documents section'}
                aria-expanded={isDocumentsExpanded}
              >
                {isDocumentsExpanded ? <ChevronDownIcon size={13} /> : <ChevronRightIcon size={13} />}
              </button>
            </div>
          </div>

          {/* Collapsible Documents Body (including upload tools and file list) */}
          {isDocumentsExpanded && (
            <div className="section-collapsible-body">
              {/* Multi-PDF Upload Dropzone */}
              <div
                className={`upload-dropzone ${isDragging ? 'dragging' : ''} ${isUploading ? 'uploading' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  type="file"
                  ref={fileInputRef}
                  accept=".pdf,.docx,.txt,.md"
                  multiple
                  style={{ display: 'none' }}
                  onChange={handleFileSelect}
                  disabled={isUploading}
                />
                <UploadCloudIcon size={24} className="upload-zone-icon" />
                <div className="upload-zone-text">
                  <strong>Upload PDFs</strong>
                  <small>Drop files or click to browse</small>
                </div>
              </div>

              {/* Staged Files Queue before upload */}
              {stagedFiles.length > 0 && (
                <div className="staged-files-panel">
                  <div className="staged-header">
                    <span>Selected ({stagedFiles.length})</span>
                    <button
                      type="button"
                      className="btn-upload-all"
                      onClick={startUpload}
                      disabled={isUploading}
                    >
                      {isUploading ? 'Uploading...' : `Upload All`}
                    </button>
                  </div>
                  <ul className="staged-list">
                    {stagedFiles.map((file, idx) => (
                      <li key={`${file.name}-${idx}`} className="staged-item">
                        <FileTextIcon size={12} className="staged-file-icon" />
                        <span className="staged-filename" title={file.name}>{file.name}</span>
                        <button
                          type="button"
                          className="staged-remove-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            removeStagedFile(idx);
                          }}
                          title="Remove file"
                        >
                          <TrashIcon size={12} />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Upload Status / Progress Bar */}
              {isUploading && (
                <div className="upload-progress-box">
                  <div className="progress-spinner-wrap">
                    <span className="spinner-sm" />
                    <span className="progress-text">Processing documents into knowledge graph...</span>
                  </div>
                  {uploadStatusMessage && <p className="progress-detail">{uploadStatusMessage}</p>}
                </div>
              )}

              {/* Upload Success/Error message if not uploading */}
              {!isUploading && uploadStatusMessage && (
                <p className="upload-feedback-message">{uploadStatusMessage}</p>
              )}

              {/* Active Collection Documents List */}
              <div className="documents-list">
                {collectionDocs.length === 0 ? (
                  <div className="empty-docs-card">
                    <p>Upload PDFs to build your knowledge graph.</p>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      className={`doc-item ${selectedDocument === '' ? 'active' : ''}`}
                      onClick={() => onSelectDocument('')}
                    >
                      <FileTextIcon size={13} className="doc-item-icon" />
                      <div className="doc-item-info">
                        <span className="doc-item-name">Combined Collection</span>
                        <small className="doc-item-meta">All {collectionDocs.length} documents</small>
                      </div>
                    </button>

                    {collectionDocs.map((doc) => {
                      const isSelected = selectedDocument === doc.document_name;
                      return (
                        <button
                          key={doc.document_name}
                          type="button"
                          className={`doc-item ${isSelected ? 'active' : ''}`}
                          onClick={() => onSelectDocument(doc.document_name)}
                        >
                          <FileTextIcon size={13} className="doc-item-icon" />
                          <div className="doc-item-info">
                            <span className="doc-item-name" title={doc.document_name}>
                              {doc.document_name}
                            </span>
                            <div className="doc-item-meta">
                              <span>{doc.passage_count} passages</span>
                              <span>•</span>
                              <span>{doc.relationship_count} relations</span>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </>
                )}
              </div>
            </div>
          )}
        </section>
      </div>
    </aside>
  );
};
