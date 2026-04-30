import React, { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut, Type } from "lucide-react";
import "react-pdf/dist/Page/TextLayer.css";
import { Document, Page, pdfjs } from "react-pdf";
import pdfWorkerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = `${pdfWorkerSrc}?v=${pdfjs.version}`;

/**
 * Optimized PdfViewer with optional text selection.
 * Canvas-only by default for performance; text layer togglable for selection.
 * Uses memoization and effect isolation to prevent flickering.
 */
export const PdfViewer = React.memo(function PdfViewer({ fileUrl, title, onSelectionChange }) {
  const containerRef = useRef(null);
  const resizeTimeoutRef = useRef(null);
  const lastSelectionRef = useRef("");
  
  const [containerWidth, setContainerWidth] = useState(640);
  const [pageNumber, setPageNumber] = useState(1);
  const [numPages, setNumPages] = useState(0);
  const [renderError, setRenderError] = useState("");
  const [zoom, setZoom] = useState(1.12);
  const [enableTextSelection, setEnableTextSelection] = useState(false);

  // Calculate page width based on container and zoom
  const pageWidth = Math.max(Math.round(containerWidth * zoom), 320);
  
  // Get device pixel ratio once (doesn't need to change per render)
  const pixelRatio = 
    typeof window !== "undefined" 
      ? Math.min(3, Math.max(window.devicePixelRatio || 1, 1.6))
      : 2;

  // Single resize handler with debounce
  useEffect(() => {
    function updateWidth() {
      if (containerRef.current) {
        const width = Math.max(containerRef.current.clientWidth - 40, 320);
        setContainerWidth(width);
      }
    }

    // Initial measurement
    updateWidth();

    // Handle window resize
    function handleResize() {
      clearTimeout(resizeTimeoutRef.current);
      resizeTimeoutRef.current = setTimeout(updateWidth, 100);
    }

    // Handle container resize via ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
      clearTimeout(resizeTimeoutRef.current);
      resizeTimeoutRef.current = setTimeout(updateWidth, 100);
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    window.addEventListener("resize", handleResize, { passive: true });

    return () => {
      clearTimeout(resizeTimeoutRef.current);
      resizeObserver.disconnect();
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  // Handle text selection within the PDF viewer
  useEffect(() => {
    function handleSelectionChange() {
      const selection = window.getSelection();
      if (!selection || !containerRef.current) return;

      // Check if selection is within our container
      const range = selection.getRangeAt(0);
      if (!range) return;

      const { commonAncestorContainer } = range;
      const container = containerRef.current;
      
      // Verify selection is within the viewer
      let node = commonAncestorContainer;
      let isWithinContainer = false;
      
      while (node) {
        if (node === container) {
          isWithinContainer = true;
          break;
        }
        node = node.parentNode;
      }

      if (!isWithinContainer) return;

      const selectedText = selection.toString().trim();
      
      if (lastSelectionRef.current !== selectedText) {
        lastSelectionRef.current = selectedText;
        onSelectionChange?.(selectedText);
      }
    }

    document.addEventListener("selectionchange", handleSelectionChange, { passive: true });

    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [onSelectionChange]);

  // Clear selection when page or file changes
  useEffect(() => {
    lastSelectionRef.current = "";
    onSelectionChange?.("");
  }, [fileUrl, pageNumber, onSelectionChange]);

  return (
    <div className="pdf-viewer-shell">
      <div className="pdf-viewer-toolbar">
        <div className="pdf-viewer-title">
          <FileText size={16} />
          <span>{title || "Compiled PDF"}</span>
        </div>
        <div className="pdf-viewer-actions">
          <button
            type="button"
            className={`pdf-nav-button ${enableTextSelection ? "active" : ""}`}
            onClick={() => setEnableTextSelection(!enableTextSelection)}
            aria-label="Toggle text selection"
            title={enableTextSelection ? "Disable text selection" : "Enable text selection"}
          >
            <Type size={16} />
          </button>
          <button
            type="button"
            className="pdf-nav-button"
            onClick={() => setZoom((current) => Math.max(0.9, Number((current - 0.08).toFixed(2))))}
            aria-label="Zoom out"
          >
            <ZoomOut size={16} />
          </button>
          <span className="pdf-page-indicator">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="pdf-nav-button"
            onClick={() => setZoom((current) => Math.min(1.9, Number((current + 0.08).toFixed(2))))}
            aria-label="Zoom in"
          >
            <ZoomIn size={16} />
          </button>
          <button
            type="button"
            className="pdf-nav-button"
            onClick={() => setPageNumber((current) => Math.max(current - 1, 1))}
            disabled={pageNumber <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="pdf-page-indicator">
            Page {pageNumber}{numPages ? ` / ${numPages}` : ""}
          </span>
          <button
            type="button"
            className="pdf-nav-button"
            onClick={() => setPageNumber((current) => Math.min(current + 1, numPages || current + 1))}
            disabled={numPages > 0 && pageNumber >= numPages}
            aria-label="Next page"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div ref={containerRef} className="pdf-viewer-canvas">
        <Document
          file={fileUrl}
          loading={<div className="report-state">Loading PDF preview...</div>}
          error={
            <div className="report-state error">
              {renderError || "Unable to render the PDF preview."}
            </div>
          }
          onLoadSuccess={({ numPages: totalPages }) => {
            setNumPages(totalPages);
            setPageNumber(1);
            setRenderError("");
          }}
          onLoadError={(error) => {
            setRenderError(error?.message || "Unable to render the PDF preview.");
          }}
        >
          <Page
            key={`page-${pageNumber}`}
            pageNumber={pageNumber}
            width={pageWidth}
            devicePixelRatio={pixelRatio}
            renderMode="canvas"
            renderAnnotationLayer={false}
            renderTextLayer={enableTextSelection}
          />
        </Document>
      </div>
    </div>
  );
});
